"""KopyKat Universal Connector Engine & Async SSRF Defense Runtime."""
from __future__ import annotations

import ipaddress
import json
import socket
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import httpcore
import httpx

MAX_SPEC_BYTES = 2_000_000
ALLOWED_SCHEMES = {"https"}
BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata",
    "metadata.google.internal",
    "host.docker.internal",
    "gateway.docker.internal",
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
            ip_obj = ipaddress.ip_address(ip_obj.strip("[]").strip())
        except ValueError as exc:
            raise SSRFError(f"Invalid IP address format: {ip_obj}") from exc
    if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped is not None:
        validate_ip_address(ip_obj.ipv4_mapped)
    if not ip_obj.is_global or ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_multicast or ip_obj.is_unspecified:
        raise SSRFError("Connector host resolves to a restricted network address.")
    for net in BLOCKED_NETWORKS:
        if ip_obj in net:
            raise SSRFError("Connector host resolves to a restricted network address.")


def resolve_and_validate_host(host: str, port: int = 443) -> str:
    host_clean = host.strip("[]").rstrip(".").lower()
    if host_clean in BLOCKED_HOSTS or host_clean.endswith((".localhost", ".local", ".internal", ".lan")):
        raise SSRFError("Local connector URLs are not permitted.")
    try:
        ip_lit = ipaddress.ip_address(host_clean)
        validate_ip_address(ip_lit)
        return str(ip_lit)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ConnectorError("Connector host could not be resolved.") from exc
    if not infos:
        raise ConnectorError("Connector host could not be resolved.")
    resolved_ips: list[str] = []
    for info in infos:
        ip_str = info[4][0]
        validate_ip_address(ip_str)
        resolved_ips.append(ip_str)
    return resolved_ips[0]


def validate_public_url(url: str, allowed_schemes: tuple[str, ...] = ("https",)) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ConnectorError("A documentation URL is required.")
    url_stripped = url.strip()
    if any(c in url_stripped for c in ("\r", "\n", "\0", "\t")) or "%0d" in url_stripped.lower() or "%0a" in url_stripped.lower() or "%00" in url_stripped.lower():
        raise ConnectorError("Invalid characters or CRLF sequence detected in URL.")
    parsed = urlparse(url_stripped)
    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ConnectorError("Connector URL contains an invalid host or port.") from exc
    if parsed.scheme.lower() not in {s.lower() for s in allowed_schemes} or not hostname:
        raise ConnectorError("Connector discovery requires an HTTPS URL.")
    if parsed.username or parsed.password or parsed.fragment:
        raise ConnectorError("Connector URLs cannot contain credentials or fragments.")
    port = port or (443 if parsed.scheme.lower() == "https" else 80)
    resolve_and_validate_host(hostname, port)
    return url_stripped


class SafePinningNetworkBackend(httpcore.AnyIOBackend):
    async def connect_tcp(self, host: str, port: int, timeout: float | None = None, local_address: str | None = None, socket_options: Any = None) -> httpcore.AsyncNetworkStream:
        pinned_ip = resolve_and_validate_host(host, port)
        return await super().connect_tcp(pinned_ip, port, timeout=timeout, local_address=local_address, socket_options=socket_options)


class SafePinningSyncNetworkBackend(httpcore.SyncBackend):
    """Synchronous counterpart used by connector discovery paths."""

    def connect_tcp(self, host: str, port: int, timeout: float | None = None, local_address: str | None = None, socket_options: Any = None) -> httpcore.NetworkStream:
        pinned_ip = resolve_and_validate_host(host, port)
        return super().connect_tcp(pinned_ip, port, timeout=timeout, local_address=local_address, socket_options=socket_options)


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

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise SSRFError(f"HTTP {self.status_code} error from {self.url}")


class SafeAsyncHTTPClient:
    def __init__(self, timeout_seconds: float = 15.0, max_response_bytes: int = MAX_SPEC_BYTES):
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self._backend = SafePinningNetworkBackend()
        self._transport = httpx.AsyncHTTPTransport()
        self._transport._pool = httpcore.AsyncConnectionPool(ssl_context=self._transport._pool._ssl_context, network_backend=self._backend)
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self, timeout_seconds: float) -> httpx.AsyncClient:
        if self._client is None or getattr(self._client, "is_closed", False) is True:
            self._client = httpx.AsyncClient(
                transport=self._transport,
                timeout=httpx.Timeout(timeout_seconds),
                follow_redirects=False,
                trust_env=False,
            )
        return self._client

    async def request(self, method: str, url: str, *, headers: Optional[dict[str, str]] = None, json_body: Optional[Any] = None, params: Optional[dict[str, Any]] = None, timeout_seconds: Optional[float] = None, max_response_bytes: Optional[int] = None, allow_redirects: bool = False) -> SafeHTTPResponse:
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
            return SafeHTTPResponse(status_code=response.status_code, headers=dict(response.headers), content=body, url=str(response.url))
        finally:
            await response.aclose()

    async def get(self, url: str, **kwargs: Any) -> SafeHTTPResponse: return await self.request("GET", url, **kwargs)
    async def post(self, url: str, **kwargs: Any) -> SafeHTTPResponse: return await self.request("POST", url, **kwargs)
    async def put(self, url: str, **kwargs: Any) -> SafeHTTPResponse: return await self.request("PUT", url, **kwargs)
    async def patch(self, url: str, **kwargs: Any) -> SafeHTTPResponse: return await self.request("PATCH", url, **kwargs)
    async def delete(self, url: str, **kwargs: Any) -> SafeHTTPResponse: return await self.request("DELETE", url, **kwargs)

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        if self._transport:
            await self._transport.aclose()

    async def __aenter__(self) -> SafeAsyncHTTPClient: return self
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: await self.close()


class SafeSyncHTTPClient:
    """Synchronous SSRF-safe client for legacy/background connector calls."""

    def __init__(self, timeout_seconds: float = 15.0, max_response_bytes: int = MAX_SPEC_BYTES):
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self._transport = httpx.HTTPTransport(retries=0)
        self._transport._pool = httpcore.ConnectionPool(
            ssl_context=self._transport._pool._ssl_context,
            network_backend=SafePinningSyncNetworkBackend(),
        )
        self._client = httpx.Client(
            transport=self._transport,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        json_body: Optional[Any] = None,
        params: Optional[dict[str, Any]] = None,
        timeout_seconds: Optional[float] = None,
        max_response_bytes: Optional[int] = None,
        allow_redirects: bool = False,
    ) -> SafeHTTPResponse:
        safe_url = validate_public_url(url, allowed_schemes=("https",))
        limit = max_response_bytes if max_response_bytes is not None else self.max_response_bytes
        timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        req_headers = {"Accept": "application/json", **(headers or {})}
        request = self._client.build_request(
            method.upper(),
            safe_url,
            headers=req_headers,
            json=json_body,
            params=params,
            timeout=httpx.Timeout(timeout),
        )
        response = self._client.send(request, stream=True)
        try:
            if 300 <= response.status_code < 400:
                if not allow_redirects:
                    raise SSRFError("Redirects are disabled for connector requests.")
                location = response.headers.get("location")
                if location:
                    validate_public_url(location)
            chunks: list[bytes] = []
            total_bytes = 0
            for chunk in response.iter_bytes():
                total_bytes += len(chunk)
                if total_bytes > limit:
                    raise SSRFError(f"Response size exceeded {limit} bytes.")
                chunks.append(chunk)
            return SafeHTTPResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                content=b"".join(chunks),
                url=str(response.url),
            )
        finally:
            response.close()

    def get(self, url: str, **kwargs: Any) -> SafeHTTPResponse:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> SafeHTTPResponse:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> SafeHTTPResponse:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> SafeHTTPResponse:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> SafeHTTPResponse:
        return self.request("DELETE", url, **kwargs)

    def close(self) -> None:
        self._client.close()
        self._transport.close()

    def __enter__(self) -> SafeSyncHTTPClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


def fetch_api_document(url: str) -> dict[str, Any]:
    try:
        with SafeSyncHTTPClient(max_response_bytes=MAX_SPEC_BYTES) as client:
            response = client.get(url, headers={"Accept": "application/json, application/yaml, text/yaml"})
            if response.status_code >= 400:
                raise ConnectorError("The API document could not be fetched.")
            document = response.json()
    except ConnectorError:
        raise
    except (httpx.HTTPError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ConnectorError("The API document must be reachable JSON/OpenAPI JSON.") from exc
    if not isinstance(document, dict):
        raise ConnectorError("Invalid API document.")
    return document


async def async_fetch_api_document(url: str) -> dict[str, Any]:
    async with SafeAsyncHTTPClient(max_response_bytes=MAX_SPEC_BYTES) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        try:
            document = resp.json()
        except ValueError as exc:
            raise ConnectorError("The API document must be JSON/OpenAPI JSON.") from exc
        if not isinstance(document, dict):
            raise ConnectorError("Invalid API document.")
        return document


def _operation_name(method: str, path: str, operation: dict[str, Any]) -> str:
    return str(operation.get("operationId") or f"{method.lower()} {path}")[:120]


def _auth_modes(document: dict[str, Any]) -> list[str]:
    schemes = document.get("components", {}).get("securitySchemes", {})
    modes: list[str] = []
    for value in schemes.values():
        if not isinstance(value, dict):
            continue
        kind = value.get("type")
        if kind == "oauth2":
            modes.append("oauth2")
        elif kind == "apiKey":
            modes.append("api_key")
        elif kind == "http" and value.get("scheme", "").lower() == "bearer":
            modes.append("bearer")
        elif kind == "http" and value.get("scheme", "").lower() == "basic":
            modes.append("basic")
    return sorted(set(modes))


def build_connector_spec(document: dict[str, Any], source_url: str) -> dict[str, Any]:
    if document.get("openapi", document.get("swagger")) is None:
        raise ConnectorError("Only OpenAPI/Swagger documents are supported.")
    base = document.get("servers", [{}])[0].get("url") if document.get("servers") else None
    if not base:
        base = f"{urlparse(source_url).scheme}://{urlparse(source_url).netloc}"
    base_url = urljoin(source_url, base)
    validate_public_url(base_url)

    operations: list[dict[str, Any]] = []
    for path, path_item in (document.get("paths") or {}).items():
        if not isinstance(path_item, dict) or not isinstance(path, str) or not path.startswith("/"):
            continue
        for method, operation in path_item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"} or not isinstance(operation, dict):
                continue
            operations.append({
                "name": _operation_name(method, path, operation),
                "method": method.upper(),
                "path": path,
                "summary": str(operation.get("summary") or operation.get("description") or "")[:500],
                "tags": [str(x)[:80] for x in operation.get("tags", [])[:10]],
                "security": operation.get("security", document.get("security", [])),
            })
    if not operations:
        raise ConnectorError("No supported HTTP operations were found.")
    return {
        "version": 1,
        "platform_name": str(document.get("info", {}).get("title") or "Custom Platform")[:120],
        "source_url": source_url,
        "base_url": base_url.rstrip("/"),
        "authentication_modes": _auth_modes(document),
        "operations": operations[:500],
        "status": "draft",
        "execution_policy": {
            "allow_arbitrary_code": False,
            "allow_redirects": False,
            "require_https": True,
            "max_operations": 500,
        },
    }


def discover_connector(source_url: str) -> dict[str, Any]:
    document = fetch_api_document(source_url)
    return build_connector_spec(document, source_url)


async def async_discover_connector(source_url: str) -> dict[str, Any]:
    document = await async_fetch_api_document(source_url)
    return build_connector_spec(document, source_url)
