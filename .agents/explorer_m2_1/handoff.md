# Milestone 2 Explorer 1 Handoff Report: Async SSRF Defense & Connector Engine

## 1. Observation

1. **Existing Codebase State**:
   - `server/connector_engine.py:27-45`: Contains `validate_public_url(url: str)` which checks scheme `https`, localhost, and performs basic IP checking with `socket.getaddrinfo`. It lacks socket pinning, complete CIDR coverage (CGNAT `100.64.0.0/10`, documentation ranges `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`, IPv4-mapped IPv6 `::ffff:0:0/96`, IPv6 ULA `fc00::/7`), and has no `SafeAsyncHTTPClient`.
   - `server/connector_engine.py:47-68`: Uses synchronous `requests.get()` in `fetch_api_document()`.
   - `server/connector_registry.py:57-83`: Uses synchronous `requests.request()` in `execute_operation()`.
   - `server/integrations.py:11-34`: Defines a duplicate helper `_validate_external_url()` using synchronous `requests` in outbound push integrations.
   - `server/database.py:139-167`: Defines `CustomConnector` and `ConnectorAuditLog` ORM models.
   - `PROJECT.md:97-113` & `SCOPE.md:4`: Specifies contract for `SafeAsyncHTTPClient`:
     - Method `request(self, method, url, *, headers, json_body, params, timeout_seconds=15.0, max_response_bytes=2_000_000, allow_redirects=False) -> SafeHTTPResponse`.
     - DNS pre-resolution, private/reserved IP rejection, socket pinning, SNI header preservation, redirect rejection, and 2MB payload cap.

2. **Environment & Dependency State**:
   - Python 3.11.9, `httpx` version 0.27.0, `httpcore` version 1.0.9 installed.
   - `httpcore.AsyncConnectionPool` accepts `network_backend: AsyncNetworkBackend | None`.
   - `httpcore.AnyIOBackend` implements `async def connect_tcp(host, port, timeout, local_address, socket_options) -> AsyncNetworkStream`.
   - `AnyIOStream.start_tls(ssl_context, server_hostname, timeout)` receives the origin hostname for TLS SNI validation.

3. **Current Test Status**:
   - `python -m pytest tests/ -v`: 65 passed, 0 failed.
   - `python -m flake8 server --count --select=E9,F63,F7,F82`: 0 errors.
   - `python tests/test_no_emojis.py`: Passed (0 emojis).

---

## 2. Logic Chain

1. **Premise 1 (SSRF / TOCTOU DNS Rebinding Threat)**: Standard HTTP client implementations that perform separate pre-flight hostname validation before passing the URL to an HTTP library remain vulnerable to DNS rebinding (TOCTOU). An attacker whose DNS server returns a valid public IP on pre-flight, and a private IP (e.g. `169.254.169.254` or `127.0.0.1`) on connection time, can bypass host validation.
2. **Premise 2 (Socket Pinning Mechanism)**: By intercepting connection establishment in `SafePinningNetworkBackend(httpcore.AnyIOBackend).connect_tcp(host, port)`:
   - The host is resolved via DNS once.
   - All returned addresses are validated against the comprehensive restricted ranges list.
   - The connection is established directly to the pre-validated IP address.
   - `stream.start_tls` and the HTTP `Host` header continue to use the original domain name, ensuring TLS certificate validation and virtual host routing succeed while eliminating DNS rebinding.
3. **Premise 3 (Redirect & Memory Exhaustion Defenses)**:
   - Disabling redirects (`follow_redirects=False`) and raising `SSRFError` on 3xx responses prevents open redirect SSRF bypasses.
   - Streaming responses (`client.stream(...)`) and capping bytes at `max_response_bytes=2_000_000` prevents memory exhaustion and decompression bombs.
4. **Premise 4 (Non-Breaking Integration)**:
   - Providing `SafeAsyncHTTPClient`, `SafeHTTPResponse`, `SSRFError`, and async discovery/execution functions while preserving synchronous signatures (`validate_public_url`, `fetch_api_document`, `build_connector_spec`, `discover_connector`, `execute_operation`) ensures all existing unit, integration, and E2E tests pass without regressions.

---

## 3. Caveats

- **IPv6 Dual-Stack Resolution**: In environments with both IPv4 and IPv6 public addresses for a domain, `socket.getaddrinfo` may return both A and AAAA records. Every returned record must be validated, and if any record resolves to a private/restricted address, the entire request is rejected.
- **Port Handling**: For HTTPS URLs, default port is 443; for HTTP URLs (when permitted), default port is 80. Custom non-standard ports (e.g. 8443) are supported and resolved appropriately.

---

## 4. Conclusion

The design for `SafeAsyncHTTPClient` is complete and verified against `httpx` 0.27.0 / `httpcore` 1.0.9:
1. Implement `SafePinningNetworkBackend` and `SafeAsyncHTTPClient` in `server/connector_engine.py`.
2. Expand IP filtering in `server/connector_engine.py` to cover all RFC 1918, RFC 3927 (including `169.254.169.254`), loopback, CGNAT (`100.64.0.0/10`), reserved (`240.0.0.0/4`, `0.0.0.0/8`), documentation/testnet ranges, IPv6 ULA/link-local/multicast, and IPv4-mapped IPv6 addresses.
3. Implement `async_execute_operation` in `server/connector_registry.py` utilizing `SafeAsyncHTTPClient`.
4. Create `tests/test_ssrf_async.py` verifying full SSRF protection, DNS rebinding elimination, redirect blocking, and 2MB response capping.

---

## 5. Verification Method

To verify the implementation once applied:
```bash
# 1. Run unit and integration test suite
python -m pytest tests/ -v

# 2. Run new SSRF async test suite
python -m pytest tests/test_ssrf_async.py -v

# 3. Verify zero emojis
python tests/test_no_emojis.py

# 4. Verify flake8 syntax check
python -m flake8 server --count --select=E9,F63,F7,F82
```
