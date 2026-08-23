# Milestone 2 Architectural Analysis: Async SSRF Defense & Autonomous Connector Engine

## 1. Executive Summary

This report delivers the technical architecture and implementation specification for **Milestone 2 (Autonomous Connectors, Real-Time Sync & Async SSRF Defense)**, focusing on:
1. `server/connector_engine.py`: Architecture of `SafeAsyncHTTPClient`, `SafeHTTPResponse`, `SSRFError`, IP pre-validation against all RFC/reserved ranges, DNS rebinding elimination via socket pinning, SNI/Host preservation, redirect blocking, 2MB streaming response capping, and OpenAPI document discovery.
2. `server/connector_registry.py`: Secure execution runtime supporting both asynchronous (`async_execute_operation`) and synchronous (`execute_operation`) dispatch with IP-pinned transport.
3. `server/database.py`: Interaction with `CustomConnector`, `ConnectorAuditLog`, `UserIntegration`, `InventoryItem`, `InventoryWebhookEvent`, and `InventorySyncLog`.
4. Test strategy for `tests/test_ssrf_async.py` and `tests/test_connectors.py`.

---

## 2. Problem Boundary & Threat Model

### 2.1 The SSRF & DNS Rebinding Vulnerability Matrix
In multi-tenant SaaS e-commerce platforms, customer-provided URLs (OpenAPI documentation URLs, webhook endpoints, platform endpoints) present severe SSRF attack surfaces:
- **Cloud Metadata Exfiltration**: Target `http://169.254.169.254/latest/meta-data/` (AWS/GCP) or `http://169.254.169.254/metadata/instance` (Azure IMDS) to steal IAM credentials and security tokens.
- **Internal Network Pivoting**: Target RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) and loopback (`127.0.0.1`, `::1`) to probe Redis, Postgres, Elasticsearch, or internal microservices.
- **Time-of-Check to Time-of-Use (TOCTOU) DNS Rebinding**: An attacker controls a domain (e.g. `rebind.attacker.com`) configured with TTL=0. During initial URL validation, the DNS server returns a public IP (`93.184.216.34`), passing the pre-flight check. When the HTTP library executes the request milliseconds later, the OS resolver queries DNS again and receives `169.254.169.254` or `127.0.0.1`.
- **Open Redirect Bypass**: A benign public server responds with a 301/302 redirect pointing to an internal IP. If the client automatically follows redirects, the internal endpoint is accessed.
- **Decompression Bombs & Uncapped Streaming DoS**: Malicious endpoints returning infinite byte streams or gzip bombs exhausting server memory and blocking event loops.

---

## 3. Architecture of `SafeAsyncHTTPClient`

### 3.1 Interface Contract
```python
class SafeHTTPResponse:
    def __init__(self, status_code: int, headers: dict[str, str], content: bytes, url: str):
        self.status_code = status_code
        self.headers = headers
        self.content = content
        self.url = url

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise SSRFError(f"HTTP {self.status_code} error from {self.url}")


class SafeAsyncHTTPClient:
    def __init__(self, timeout_seconds: float = 15.0, max_response_bytes: int = 2_000_000):
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        json_body: Optional[Any] = None,
        params: Optional[dict[str, Any]] = None,
        timeout_seconds: Optional[float] = None,
        max_response_bytes: Optional[int] = None,
        allow_redirects: bool = False
    ) -> SafeHTTPResponse: ...

    async def get(self, url: str, **kwargs) -> SafeHTTPResponse: ...
    async def post(self, url: str, **kwargs) -> SafeHTTPResponse: ...
    async def put(self, url: str, **kwargs) -> SafeHTTPResponse: ...
    async def patch(self, url: str, **kwargs) -> SafeHTTPResponse: ...
    async def delete(self, url: str, **kwargs) -> SafeHTTPResponse: ...
    async def __aenter__(self) -> SafeAsyncHTTPClient: return self
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None: ...
```

---

### 3.2 IP Validation Matrix & Blocked Subnets
Every resolved IP address (IPv4 and IPv6) must be strictly checked against:
1. `ip.is_global` (must be `True`).
2. Standard category flags: `ip.is_private`, `ip.is_loopback`, `ip.is_link_local`, `ip.is_reserved`, `ip.is_multicast`, `ip.is_unspecified`.
3. Complete CIDR blacklist:
   - `0.0.0.0/8` (Current network)
   - `10.0.0.0/8` (RFC 1918 Private)
   - `100.64.0.0/10` (RFC 6598 Carrier-Grade NAT)
   - `127.0.0.0/8` (RFC 1122 Loopback)
   - `169.254.0.0/16` (RFC 3927 Link-Local / Cloud Metadata `169.254.169.254`)
   - `172.16.0.0/12` (RFC 1918 Private)
   - `192.0.0.0/24` (RFC 6890 IETF Protocol Assignments)
   - `192.0.2.0/24` (RFC 5737 TEST-NET-1 Documentation)
   - `192.88.99.0/24` (RFC 7526 6to4 Anycast Relay)
   - `192.168.0.0/16` (RFC 1918 Private)
   - `198.18.0.0/15` (RFC 2544 Benchmarking)
   - `198.51.100.0/24` (RFC 5737 TEST-NET-2 Documentation)
   - `203.0.113.0/24` (RFC 5737 TEST-NET-3 Documentation)
   - `224.0.0.0/4` (RFC 5771 Multicast)
   - `240.0.0.0/4` (RFC 1112 Reserved / Future use)
   - `255.255.255.255/32` (Limited Broadcast)
   - `::/128` (Unspecified IPv6)
   - `::1/128` (Loopback IPv6)
   - `::ffff:0:0/96` (IPv4-mapped IPv6 — extract `ip.ipv4_mapped` and re-validate against IPv4 rules)
   - `64:ff9b::/96` and `64:ff9b:1::/48` (IPv4/IPv6 translation)
   - `100::/64` (Discard-only)
   - `2001:db8::/32` (Documentation IPv6)
   - `2002::/16` (6to4)
   - `fc00::/7` (RFC 4193 Unique Local Address - ULA)
   - `fe80::/10` (Link-Local unicast IPv6)
   - `ff00::/8` (Multicast IPv6)

---

### 3.3 Eliminating TOCTOU DNS Rebinding via Custom `AsyncNetworkBackend`
To eliminate TOCTOU rebinding while preserving TLS SNI and Host header:
1. `httpcore.AsyncConnectionPool` delegates socket connection to an `AsyncNetworkBackend` (`httpcore.AnyIOBackend`).
2. We create `SafePinningNetworkBackend(httpcore.AnyIOBackend)`.
3. In `async def connect_tcp(self, host: str, port: int, timeout=None, local_address=None, socket_options=None)`:
   - Intercept `host` and `port`.
   - Call `socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)`.
   - Iterate over ALL resolved IP addresses. If ANY address matches a restricted range, raise `SSRFError`.
   - Select the validated IP address (e.g. `"93.184.216.34"`).
   - Call `await super().connect_tcp(validated_ip, port, timeout=timeout, local_address=local_address, socket_options=socket_options)`.
4. Because `httpcore.AsyncHTTP11Connection` invokes `stream.start_tls(ssl_context=..., server_hostname=origin.host.decode("ascii"))`, the original hostname is passed as SNI. TLS certificate validation and server virtual hosting succeed against the domain name, while the underlying TCP socket is pinned to the verified IP.

---

### 3.4 Redirect Blocking & 2MB Streaming Cap
- **Redirects**: `follow_redirects=False` is set on `httpx.AsyncClient`. When a response is received, if `300 <= response.status_code < 400` and `allow_redirects is False`, `SafeAsyncHTTPClient` raises `SSRFError("Redirects are disabled to prevent SSRF redirection attacks.")`.
- **Response Capping**: Instead of buffering the entire payload into memory, `client.stream(method, url, ...)` is consumed chunk-by-chunk via `aiter_bytes()`. If cumulative bytes exceed `max_response_bytes` (default 2,000,000 bytes / 2MB), connection is aborted and `SSRFError` is raised.

---

## 4. Autonomous Connector Engine (`server/connector_engine.py`)

### 4.1 Component Responsibilities
- `validate_public_url(url: str, allowed_schemes: tuple = ("https",)) -> str`: Validates scheme, hostname, pre-resolves DNS, rejects private/restricted IPs.
- `build_connector_spec(document: dict[str, Any], source_url: str) -> dict[str, Any]`: Parses OpenAPI/Swagger 2.0/3.0/3.1 specs, sanitizes operation names, extracts authentication modes (`oauth2`, `api_key`, `bearer`, `basic`), and formats execution policies.
- `fetch_api_document(url: str) -> dict[str, Any]`: Synchronous safe fetch for backward compatibility.
- `async def async_fetch_api_document(url: str) -> dict[str, Any]`: Asynchronous safe fetch using `SafeAsyncHTTPClient`.
- `discover_connector(source_url: str) -> dict[str, Any]`: Sync entry point.
- `async def async_discover_connector(source_url: str) -> dict[str, Any]`: Async entry point.

---

## 5. Connector Execution Runtime (`server/connector_registry.py`)

### 5.1 Component Responsibilities
- `validate_connector_spec(spec: dict[str, Any]) -> dict[str, Any]`: Verifies version=1, allowed status, 1-500 operations, valid HTTP methods (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`), clean paths (starts with `/`, no double slashes `//`, no embedded query string `?`).
- `find_operation(spec: dict[str, Any], name: str) -> dict[str, Any]`: Locates specified operation in spec.
- `execute_operation(spec: dict[str, Any], operation_name: str, ...) -> dict[str, Any]`: Synchronous execution wrapper.
- `async def async_execute_operation(spec: dict[str, Any], operation_name: str, *, path_params: dict | None = None, query: dict | None = None, json_body: dict | None = None, headers: dict | None = None, auth_headers: dict | None = None, timeout_seconds: float = 15.0) -> dict[str, Any]`: Async execution using `SafeAsyncHTTPClient`.

---

## 6. Proposed Code Changes & Implementation Blueprint

### 6.1 `server/connector_engine.py` Implementation Blueprint
```python
# server/connector_engine.py
from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpcore
import httpx
import requests

MAX_SPEC_BYTES = 2_000_000
ALLOWED_SCHEMES = {"https"}
BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "127.0.0.1",
    "::1",
}

BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.88.99.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::ffff:0:0/96"),
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
    ipaddress.ip_network("100::/64"),
    ipaddress.ip_network("2001:db8::/32"),
    ipaddress.ip_network("2002::/16"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
]


class ConnectorError(ValueError):
    pass


class SSRFError(ConnectorError):
    pass


def validate_ip_address(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address | str) -> None:
    if isinstance(ip_obj, str):
        try:
            ip_obj = ipaddress.ip_address(ip_obj.strip("[]"))
        except ValueError as exc:
            raise SSRFError(f"Invalid IP address format: {ip_obj}") from exc

    # If IPv4-mapped IPv6, check inner IPv4
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
        validate_ip_address(ip_obj.ipv4_mapped)

    if not ip_obj.is_global or ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_multicast or ip_obj.is_unspecified:
        raise SSRFError("Connector host resolves to a restricted network address.")

    for net in BLOCKED_NETWORKS:
        if ip_obj in net:
            raise SSRFError("Connector host resolves to a restricted network address.")


def resolve_and_validate_host(host: str, port: int = 443) -> str:
    host_clean = host.strip("[]").rstrip(".").lower()
    if host_clean in BLOCKED_HOSTS or host_clean.endswith(".localhost") or host_clean.endswith(".local") or host_clean.endswith(".internal"):
        raise ConnectorError("Local connector URLs are not permitted.")

    # Direct IP literal check
    try:
        ip = ipaddress.ip_address(host_clean)
        validate_ip_address(ip)
        return str(ip)
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ConnectorError("Connector host could not be resolved.") from exc

    resolved_ips: list[str] = []
    for info in infos:
        ip_str = info[4][0]
        try:
            validate_ip_address(ip_str)
            resolved_ips.append(ip_str)
        except SSRFError as exc:
            raise exc

    if not resolved_ips:
        raise ConnectorError("Connector host could not be resolved.")
    return resolved_ips[0]


def validate_public_url(url: str, allowed_schemes: tuple[str, ...] = ("https",)) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ConnectorError("A documentation URL is required.")
    parsed = urlparse(url.strip())
    schemes = set(allowed_schemes)
    if parsed.scheme.lower() not in schemes or not parsed.hostname:
        raise ConnectorError("Connector discovery requires an HTTPS URL.")
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    resolve_and_validate_host(parsed.hostname, port)
    return url.strip()


class SafePinningNetworkBackend(httpcore.AnyIOBackend):
    async def connect_tcp(self, host: str, port: int, timeout=None, local_address=None, socket_options=None):
        pinned_ip = resolve_and_validate_host(host, port)
        return await super().connect_tcp(pinned_ip, port, timeout=timeout, local_address=local_address, socket_options=socket_options)


class SafeHTTPResponse:
    def __init__(self, status_code: int, headers: dict[str, str], content: bytes, url: str):
        self.status_code = status_code
        self.headers = headers
        self.content = content
        self.url = url

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise SSRFError(f"HTTP {self.status_code} error from {self.url}")


class SafeAsyncHTTPClient:
    def __init__(self, timeout_seconds: float = 15.0, max_response_bytes: int = MAX_SPEC_BYTES):
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self._backend = SafePinningNetworkBackend()
        self._transport = httpx.AsyncHTTPTransport()
        self._transport._pool = httpcore.AsyncConnectionPool(
            ssl_context=self._transport._pool._ssl_context,
            network_backend=self._backend
        )
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self, timeout_seconds: float) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                transport=self._transport,
                timeout=httpx.Timeout(timeout_seconds),
                follow_redirects=False
            )
        return self._client

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        json_body: Optional[Any] = None,
        params: Optional[dict[str, Any]] = None,
        timeout_seconds: Optional[float] = None,
        max_response_bytes: Optional[int] = None,
        allow_redirects: bool = False
    ) -> SafeHTTPResponse:
        safe_url = validate_public_url(url)
        timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        limit = max_response_bytes if max_response_bytes is not None else self.max_response_bytes

        client = self._get_client(timeout)
        req_headers = {"Accept": "application/json, application/yaml, text/yaml", **(headers or {})}

        req = client.build_request(method.upper(), safe_url, headers=req_headers, json=json_body, params=params)
        response = await client.send(req, stream=True)

        try:
            if 300 <= response.status_code < 400:
                if not allow_redirects:
                    raise SSRFError("Redirects are disabled during connector discovery.")
                location = response.headers.get("location")
                if location:
                    validate_public_url(location)

            chunks: list[bytes] = []
            total_bytes = 0
            async for chunk in response.aiter_bytes():
                total_bytes += len(chunk)
                if total_bytes > limit:
                    raise SSRFError(f"Response size exceeded {limit} bytes.")
                chunks.append(chunk)

            body = b"".join(chunks)
            resp_headers = dict(response.headers)
            return SafeHTTPResponse(
                status_code=response.status_code,
                headers=resp_headers,
                content=body,
                url=str(response.url)
            )
        finally:
            await response.aclose()

    async def get(self, url: str, **kwargs) -> SafeHTTPResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> SafeHTTPResponse:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs) -> SafeHTTPResponse:
        return await self.request("PUT", url, **kwargs)

    async def patch(self, url: str, **kwargs) -> SafeHTTPResponse:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs) -> SafeHTTPResponse:
        return await self.request("DELETE", url, **kwargs)

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        if self._transport:
            await self._transport.aclose()

    async def __aenter__(self) -> SafeAsyncHTTPClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
```

---

## 7. Test Plan for `tests/test_ssrf_async.py` & `tests/test_connectors.py`

### 7.1 Proposed Test Cases for `tests/test_ssrf_async.py`
1. `test_safe_async_client_blocks_ipv4_private_subnets`:
   - Validates `10.0.0.1`, `172.16.0.1`, `192.168.1.1` raise `SSRFError`/`ConnectorError`.
2. `test_safe_async_client_blocks_link_local_and_metadata`:
   - Validates `169.254.169.254`, `169.254.0.1` raise `SSRFError`.
3. `test_safe_async_client_blocks_loopback_variations`:
   - Validates `127.0.0.1`, `127.255.255.254`, `localhost`, `test.localhost`, `[::1]` raise `ConnectorError`.
4. `test_safe_async_client_blocks_cgnat_and_reserved`:
   - Validates `100.64.0.1`, `240.0.0.1`, `0.0.0.0` raise `ConnectorError`.
5. `test_safe_async_client_blocks_ipv6_special_ranges`:
   - Validates `[fe80::1]`, `[fc00::1]`, `[fd00::1]`, `[ff02::1]`, `[::ffff:127.0.0.1]` raise `ConnectorError`.
6. `test_safe_async_client_blocks_redirects_to_private_targets`:
   - Mock endpoint returning 302 redirect to `https://169.254.169.254/` verifies `SSRFError` is raised.
7. `test_safe_async_client_enforces_2mb_streaming_cap`:
   - Mock streaming endpoint returning >2,000,000 bytes verifies exception before memory exhaustion.
8. `test_safe_async_client_dns_rebinding_socket_pinning`:
   - Verifies that socket connection connects directly to pre-resolved IP while `server_hostname` matches origin domain.

---

## 8. Summary of Findings & Next Steps

1. **Zero Breaking Changes**: The architecture maintains complete backward compatibility for synchronous `validate_public_url`, `build_connector_spec`, and `discover_connector`.
2. **Robust Defense**: `SafePinningNetworkBackend` eliminates DNS rebinding TOCTOU by design, as connection is pinned to the pre-validated IP address at the `httpcore` network backend layer.
3. **Clean Asynchronous Runtime**: `SafeAsyncHTTPClient` provides async non-blocking execution throughout `server/connector_engine.py`, `server/connector_registry.py`, and `server/integrations.py`.
