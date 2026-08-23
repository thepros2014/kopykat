import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from server.connector_engine import (
    ConnectorError, MAX_SPEC_BYTES, SafeAsyncHTTPClient, SafeHTTPResponse,
    SafePinningNetworkBackend, SSRFError, resolve_and_validate_host, validate_ip_address, validate_public_url
)

@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254",
    "100.64.0.1", "0.0.0.0", "224.0.0.1", "240.0.0.1", "255.255.255.255",
    "192.0.2.1", "198.51.100.1", "203.0.113.1", "::1", "::", "fe80::1", "fc00::1",
    "ff02::1", "2001:db8::1", "::ffff:127.0.0.1", "::ffff:10.0.0.1"
])
def test_validate_ip_address_blocks_restricted(ip):
    with pytest.raises(SSRFError):
        validate_ip_address(ip)

@pytest.mark.parametrize("ip", ["93.184.216.34", "8.8.8.8", "1.1.1.1"])
def test_validate_ip_address_allows_public(ip):
    validate_ip_address(ip)

def test_validate_ip_address_invalid():
    with pytest.raises(SSRFError):
        validate_ip_address("invalid-ip")

@pytest.mark.parametrize("h", ["localhost", "test.localhost", "svc.local", "db.internal"])
def test_resolve_and_validate_host_blocks_local(h):
    with pytest.raises(SSRFError):
        resolve_and_validate_host(h)

def test_resolve_and_validate_host_public(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 443))])
    assert resolve_and_validate_host("api.example.com", 443) == "93.184.216.34"

def test_resolve_and_validate_host_rebind(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(None, None, None, None, ("169.254.169.254", 443))])
    with pytest.raises(SSRFError):
        resolve_and_validate_host("rebind.example.com", 443)

def test_validate_public_url():
    with pytest.raises(ConnectorError):
        validate_public_url("http://insecure.com")
    with pytest.raises(ConnectorError):
        validate_public_url("")

def test_safe_http_response():
    resp = SafeHTTPResponse(200, {"content-type": "application/json"}, b'{"ok": true}', "https://api.com")
    assert resp.status_code == 200 and resp.is_success and resp.ok
    assert resp.text == '{"ok": true}' and resp.json() == {"ok": True}
    resp.raise_for_status()
    err_resp = SafeHTTPResponse(404, {}, b"error", "https://api.com")
    with pytest.raises(SSRFError):
        err_resp.raise_for_status()

@pytest.mark.asyncio
async def test_safe_async_client_lifecycle():
    async with SafeAsyncHTTPClient() as client:
        assert client.timeout_seconds == 15.0
        assert client.max_response_bytes == MAX_SPEC_BYTES
        with pytest.raises(ConnectorError):
            await client.get("https://127.0.0.1/test")

@pytest.mark.asyncio
async def test_safe_async_client_blocks_redirects(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 443))])
    mock_resp = MagicMock()
    mock_resp.status_code = 302
    mock_resp.headers = {"location": "https://169.254.169.254/"}
    mock_resp.url = "https://api.example.com"
    async def aiter(): yield b"red"
    mock_resp.aiter_bytes = aiter
    mock_resp.aclose = AsyncMock()
    mock_client = MagicMock()
    mock_client.build_request = MagicMock()
    mock_client.send = AsyncMock(return_value=mock_resp)
    async with SafeAsyncHTTPClient() as c:
        c._client = mock_client
        with pytest.raises(SSRFError):
            await c.get("https://api.example.com")

@pytest.mark.asyncio
async def test_safe_async_client_caps_2mb(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 443))])
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {}
    mock_resp.url = "https://api.example.com"
    async def aiter():
        yield b"X" * 1_000_000
        yield b"X" * 1_000_000
        yield b"overflow"
    mock_resp.aiter_bytes = aiter
    mock_resp.aclose = AsyncMock()
    mock_client = MagicMock()
    mock_client.build_request = MagicMock()
    mock_client.send = AsyncMock(return_value=mock_resp)
    async with SafeAsyncHTTPClient(max_response_bytes=2_000_000) as c:
        c._client = mock_client
        with pytest.raises(SSRFError):
            await c.get("https://api.example.com")

@pytest.mark.asyncio
async def test_safe_async_client_success(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 443))])
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.url = "https://api.example.com"
    async def aiter(): yield b'{"status": "ok"}'
    mock_resp.aiter_bytes = aiter
    mock_resp.aclose = AsyncMock()
    mock_client = MagicMock()
    mock_client.build_request = MagicMock()
    mock_client.send = AsyncMock(return_value=mock_resp)
    async with SafeAsyncHTTPClient() as c:
        c._client = mock_client
        resp = await c.get("https://api.example.com")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

@pytest.mark.asyncio
async def test_safe_pinning_backend_connect(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 443))])
    backend = SafePinningNetworkBackend()
    with patch("httpcore.AnyIOBackend.connect_tcp", new_callable=AsyncMock) as m:
        m.return_value = MagicMock()
        await backend.connect_tcp("api.example.com", 443)
        m.assert_called_once_with("93.184.216.34", 443, timeout=None, local_address=None, socket_options=None)

