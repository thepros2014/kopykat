"""Empirical Stress-Test & Challenge Suite for Milestone 2.

Tests Async SSRF Defense, CIDR Blocklists, Redirect Blocking, 2MB Limits,
Socket Pinning, Platform Connectors HMAC, Edge Cases, Error Mapping,
Zero-Emoji Invariant, and AST / Code Quality.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import os
import re
import socket
import sys
from typing import Any, Dict, List, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure server module is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from server.connector_engine import (
    ALLOWED_SCHEMES,
    BLOCKED_HOSTS,
    BLOCKED_NETWORKS,
    ConnectorError,
    MAX_SPEC_BYTES,
    SSRFError,
    SafeAsyncHTTPClient,
    SafeHTTPResponse,
    SafePinningNetworkBackend,
    build_connector_spec,
    fetch_api_document,
    resolve_and_validate_host,
    validate_ip_address,
    validate_public_url,
)
from server.connector_registry import (
    ALLOWED_METHODS,
    async_execute_operation,
    execute_operation,
    find_operation,
    validate_connector_spec,
)
from server.integrations import (
    AmazonConnector,
    ConnectorAuthError,
    ConnectorError as IntegrationsConnectorError,
    ConnectorNetworkError,
    ConnectorRateLimitError,
    ConnectorValidationError,
    EBayConnector,
    EtsyConnector,
    PlatformConnector,
    ShopifyConnector,
    TemuConnector,
    TikTokShopConnector,
    WalmartConnector,
    WooCommerceConnector,
    _handle_http_errors,
    get_connector,
)


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors: List[str] = []

    def record_pass(self, test_name: str):
        self.passed += 1
        print(f"  [PASS] {test_name}")

    def record_fail(self, test_name: str, reason: str):
        self.failed += 1
        self.errors.append(f"{test_name}: {reason}")
        print(f"  [FAIL] {test_name}: {reason}")


result = TestResult()


def test_restricted_cidr_ranges():
    print("\n--- 1. Testing Restricted CIDR Ranges & IP Pre-Validation ---")
    restricted_ips = [
        "127.0.0.1",
        "127.0.0.2",
        "127.255.255.255",
        "10.0.0.1",
        "10.254.0.1",
        "172.16.0.1",
        "172.31.255.254",
        "192.168.1.1",
        "192.168.254.254",
        "169.254.169.254",
        "169.254.1.1",
        "100.64.0.1",
        "240.0.0.1",
        "0.0.0.0",
        "192.0.2.1",
        "198.51.100.1",
        "203.0.113.1",
        "224.0.0.1",
        "255.255.255.255",
        "::1",
        "::",
        "fe80::1",
        "fc00::1",
        "fd00::1",
        "ff02::1",
        "2001:db8::1",
        "::ffff:127.0.0.1",
        "::ffff:10.0.0.1",
        "::ffff:169.254.169.254",
        "::ffff:192.168.1.1",
        "::ffff:172.16.0.1",
    ]

    for ip in restricted_ips:
        try:
            validate_ip_address(ip)
            result.record_fail(f"IP Block {ip}", "Expected SSRFError but validate_ip_address passed")
        except SSRFError:
            result.record_pass(f"IP Block {ip}")
        except Exception as exc:
            result.record_fail(f"IP Block {ip}", f"Unexpected exception type: {type(exc).__name__}: {exc}")

    public_ips = ["93.184.216.34", "8.8.8.8", "1.1.1.1", "104.244.42.1", "2606:2800:220:1:248:1893:25c8:1946"]
    for ip in public_ips:
        try:
            validate_ip_address(ip)
            result.record_pass(f"Public IP Allowed {ip}")
        except Exception as exc:
            result.record_fail(f"Public IP Allowed {ip}", f"Unexpected exception: {exc}")

    invalid_ips = ["not_an_ip", "999.999.999.999", "1.2.3.4.5", "http://example.com"]
    for inv in invalid_ips:
        try:
            validate_ip_address(inv)
            result.record_fail(f"Invalid IP Format {inv}", "Expected SSRFError but passed")
        except SSRFError:
            result.record_pass(f"Invalid IP Format {inv}")
        except Exception as exc:
            result.record_fail(f"Invalid IP Format {inv}", f"Unexpected exception: {exc}")


def test_hostname_resolution_and_dns_rebinding():
    print("\n--- 2. Testing Hostname Resolution & DNS Rebinding Defenses ---")
    local_hosts = ["localhost", "localhost.localdomain", "test.localhost", "app.local", "db.internal", "router.lan"]
    for host in local_hosts:
        try:
            resolve_and_validate_host(host)
            result.record_fail(f"Local Host Block {host}", "Expected SSRFError but passed")
        except SSRFError:
            result.record_pass(f"Local Host Block {host}")
        except Exception as exc:
            result.record_fail(f"Local Host Block {host}", f"Unexpected exception: {exc}")

    # Test DNS Rebinding simulation: domain resolving to AWS metadata or loopback
    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("169.254.169.254", 443))]):
        try:
            resolve_and_validate_host("rebind.attacker.com", 443)
            result.record_fail("DNS Rebinding to Metadata (169.254.169.254)", "Expected SSRFError but passed")
        except SSRFError:
            result.record_pass("DNS Rebinding to Metadata (169.254.169.254)")

    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 443))]):
        try:
            resolve_and_validate_host("rebind.attacker.com", 443)
            result.record_fail("DNS Rebinding to Loopback (127.0.0.1)", "Expected SSRFError but passed")
        except SSRFError:
            result.record_pass("DNS Rebinding to Loopback (127.0.0.1)")

    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.5", 443))]):
        try:
            resolve_and_validate_host("rebind.attacker.com", 443)
            result.record_fail("DNS Rebinding to RFC1918 (10.0.0.5)", "Expected SSRFError but passed")
        except SSRFError:
            result.record_pass("DNS Rebinding to RFC1918 (10.0.0.5)")

    # Legitimate public resolution
    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]):
        try:
            resolved = resolve_and_validate_host("api.example.com", 443)
            if resolved == "93.184.216.34":
                result.record_pass("Public Host Resolution (api.example.com -> 93.184.216.34)")
            else:
                result.record_fail("Public Host Resolution", f"Expected 93.184.216.34 but got {resolved}")
        except Exception as exc:
            result.record_fail("Public Host Resolution", f"Unexpected exception: {exc}")


async def test_redirect_rejection_async():
    print("\n--- 3. Testing Redirect Rejection (301, 302, 307, 308) ---")
    redirect_codes = [301, 302, 307, 308]

    for code in redirect_codes:
        mock_resp = MagicMock()
        mock_resp.status_code = code
        mock_resp.headers = {"location": "https://169.254.169.254/latest/meta-data/"}
        mock_resp.url = "https://api.example.com/redirect"
        async def aiter():
            yield b"Redirecting"
        mock_resp.aiter_bytes = aiter
        mock_resp.aclose = AsyncMock()

        mock_client = MagicMock()
        mock_client.build_request = MagicMock()
        mock_client.send = AsyncMock(return_value=mock_resp)

        with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]):
            async with SafeAsyncHTTPClient() as client:
                client._client = mock_client
                try:
                    await client.get("https://api.example.com/redirect")
                    result.record_fail(f"Redirect Rejection HTTP {code}", "Expected SSRFError but request succeeded")
                except SSRFError:
                    result.record_pass(f"Redirect Rejection HTTP {code}")
                except Exception as exc:
                    result.record_fail(f"Redirect Rejection HTTP {code}", f"Unexpected exception: {exc}")


async def test_streaming_response_size_limits():
    print("\n--- 4. Testing Streaming Response Cap (2,000,000 Bytes) ---")
    # Exact limit (2,000,000 bytes) should succeed
    mock_resp_exact = MagicMock()
    mock_resp_exact.status_code = 200
    mock_resp_exact.headers = {"content-type": "application/octet-stream"}
    mock_resp_exact.url = "https://api.example.com/spec"
    async def aiter_exact():
        yield b"A" * 1_000_000
        yield b"B" * 1_000_000
    mock_resp_exact.aiter_bytes = aiter_exact
    mock_resp_exact.aclose = AsyncMock()

    mock_client_exact = MagicMock()
    mock_client_exact.build_request = MagicMock()
    mock_client_exact.send = AsyncMock(return_value=mock_resp_exact)

    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]):
        async with SafeAsyncHTTPClient(max_response_bytes=2_000_000) as client:
            client._client = mock_client_exact
            try:
                resp = await client.get("https://api.example.com/spec")
                if len(resp.content) == 2_000_000 and resp.status_code == 200:
                    result.record_pass("Exact 2,000,000 byte response accepted")
                else:
                    result.record_fail("Exact 2MB response", f"Unexpected content length: {len(resp.content)}")
            except Exception as exc:
                result.record_fail("Exact 2MB response", f"Unexpected exception: {exc}")

    # Exceeding limit (2,000,001 bytes) should raise SSRFError
    mock_resp_overflow = MagicMock()
    mock_resp_overflow.status_code = 200
    mock_resp_overflow.headers = {"content-type": "application/octet-stream"}
    mock_resp_overflow.url = "https://api.example.com/spec"
    async def aiter_overflow():
        yield b"A" * 1_000_000
        yield b"B" * 1_000_000
        yield b"X"  # 2,000,001st byte
    mock_resp_overflow.aiter_bytes = aiter_overflow
    mock_resp_overflow.aclose = AsyncMock()

    mock_client_overflow = MagicMock()
    mock_client_overflow.build_request = MagicMock()
    mock_client_overflow.send = AsyncMock(return_value=mock_resp_overflow)

    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]):
        async with SafeAsyncHTTPClient(max_response_bytes=2_000_000) as client:
            client._client = mock_client_overflow
            try:
                await client.get("https://api.example.com/spec")
                result.record_fail("2,000,001 byte overflow", "Expected SSRFError on 2MB + 1 byte but succeeded")
            except SSRFError as exc:
                if "Response size exceeded" in str(exc):
                    result.record_pass("2,000,001 byte overflow correctly rejected with SSRFError")
                else:
                    result.record_fail("2MB overflow message", f"Unexpected error message: {exc}")
            except Exception as exc:
                result.record_fail("2MB overflow", f"Unexpected exception: {exc}")


async def test_socket_pinning():
    print("\n--- 5. Testing Socket Pinning & SafePinningNetworkBackend ---")
    backend = SafePinningNetworkBackend()
    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("93.184.216.34", 443))]):
        with patch("httpcore.AnyIOBackend.connect_tcp", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = MagicMock()
            await backend.connect_tcp("api.example.com", 443)
            try:
                mock_connect.assert_called_once_with("93.184.216.34", 443, timeout=None, local_address=None, socket_options=None)
                result.record_pass("SafePinningNetworkBackend pins TCP connection to resolved IP (93.184.216.34)")
            except AssertionError as err:
                result.record_fail("SafePinningNetworkBackend pin check", str(err))

    # Test that backend blocks connection when hostname resolves to private IP
    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("127.0.0.1", 443))]):
        with patch("httpcore.AnyIOBackend.connect_tcp", new_callable=AsyncMock) as mock_connect:
            try:
                await backend.connect_tcp("rebind-target.local", 443)
                result.record_fail("SafePinningNetworkBackend private IP block", "Expected SSRFError but connect_tcp succeeded")
            except SSRFError:
                result.record_pass("SafePinningNetworkBackend rejects private IP resolution before TCP connection")
                mock_connect.assert_not_called()


def test_platform_webhook_hmac_signatures():
    print("\n--- 6. Testing Platform Connectors Webhook HMAC Signatures ---")
    payload = b'{"event": "inventory_level_update", "sku": "SHIRT-BLK-M", "delta": -1}'
    secret = "super_secret_webhook_key_12345"

    # 1. Shopify: Base64 HMAC-SHA256
    shopify_conn = ShopifyConnector()
    shopify_valid_sig = base64.b64encode(hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()).decode("utf-8")
    
    # Valid
    assert shopify_conn.verify_webhook({"X-Shopify-Hmac-SHA256": shopify_valid_sig}, payload, secret) is True
    result.record_pass("Shopify webhook HMAC valid signature")
    # Invalid signature
    assert shopify_conn.verify_webhook({"X-Shopify-Hmac-SHA256": "bad_sig_base64=="}, payload, secret) is False
    result.record_pass("Shopify webhook HMAC invalid signature rejected")
    # Tampered payload
    assert shopify_conn.verify_webhook({"X-Shopify-Hmac-SHA256": shopify_valid_sig}, payload + b"tamper", secret) is False
    result.record_pass("Shopify webhook HMAC tampered payload rejected")
    # Missing header
    assert shopify_conn.verify_webhook({}, payload, secret) is False
    result.record_pass("Shopify webhook HMAC missing header rejected")
    # Empty secret
    assert shopify_conn.verify_webhook({"X-Shopify-Hmac-SHA256": shopify_valid_sig}, payload, "") is False
    result.record_pass("Shopify webhook HMAC empty secret rejected")

    # 2. Amazon: Hex HMAC-SHA256
    amazon_conn = AmazonConnector()
    amazon_valid_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    assert amazon_conn.verify_webhook({"x-amz-signature": amazon_valid_sig}, payload, secret) is True
    assert amazon_conn.verify_webhook({"X-Amzn-Signature": amazon_valid_sig}, payload, secret) is True
    assert amazon_conn.verify_webhook({"signature": amazon_valid_sig}, payload, secret) is True
    result.record_pass("Amazon webhook HMAC valid signature across header aliases")
    assert amazon_conn.verify_webhook({"x-amz-signature": "deadbeef1234"}, payload, secret) is False
    result.record_pass("Amazon webhook HMAC invalid signature rejected")
    assert amazon_conn.verify_webhook({"x-amz-signature": amazon_valid_sig}, payload + b"tamper", secret) is False
    result.record_pass("Amazon webhook HMAC tampered payload rejected")

    # 3. Etsy: Hex HMAC-SHA256
    etsy_conn = EtsyConnector()
    etsy_valid_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    assert etsy_conn.verify_webhook({"x-etsy-signature": etsy_valid_sig}, payload, secret) is True
    assert etsy_conn.verify_webhook({"x-etsy-hmac-sha256": etsy_valid_sig}, payload, secret) is True
    result.record_pass("Etsy webhook HMAC valid signature")
    assert etsy_conn.verify_webhook({"x-etsy-signature": "invalid_hex"}, payload, secret) is False
    result.record_pass("Etsy webhook HMAC invalid signature rejected")

    # 4. TikTok Shop: Hex HMAC-SHA256
    tiktok_conn = TikTokShopConnector()
    tiktok_valid_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    assert tiktok_conn.verify_webhook({"authorization": tiktok_valid_sig}, payload, secret) is True
    assert tiktok_conn.verify_webhook({"X-TTS-Signature": tiktok_valid_sig}, payload, secret) is True
    result.record_pass("TikTok Shop webhook HMAC valid signature")
    assert tiktok_conn.verify_webhook({"authorization": "invalid_sig"}, payload, secret) is False
    result.record_pass("TikTok Shop webhook HMAC invalid signature rejected")

    # 5. eBay: Hex HMAC-SHA256
    ebay_conn = EBayConnector()
    ebay_valid_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    assert ebay_conn.verify_webhook({"x-ebay-signature": ebay_valid_sig}, payload, secret) is True
    result.record_pass("eBay webhook HMAC valid signature")
    assert ebay_conn.verify_webhook({"x-ebay-signature": "bad_ebay_sig"}, payload, secret) is False
    result.record_pass("eBay webhook HMAC invalid signature rejected")

    # 6. Walmart: Hex HMAC-SHA256
    walmart_conn = WalmartConnector()
    walmart_valid_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    assert walmart_conn.verify_webhook({"x-walmart-signature": walmart_valid_sig}, payload, secret) is True
    assert walmart_conn.verify_webhook({"x-walmart-signature": "bad_sig"}, payload, secret) is False
    result.record_pass("Walmart webhook HMAC signature check")

    # 7. Temu: Hex HMAC-SHA256
    temu_conn = TemuConnector()
    temu_valid_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    assert temu_conn.verify_webhook({"x-temu-signature": temu_valid_sig}, payload, secret) is True
    assert temu_conn.verify_webhook({"x-temu-signature": "bad_sig"}, payload, secret) is False
    result.record_pass("Temu webhook HMAC signature check")

    # 8. WooCommerce: Base64 HMAC-SHA256
    woo_conn = WooCommerceConnector()
    woo_valid_sig = base64.b64encode(hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()).decode("utf-8")
    assert woo_conn.verify_webhook({"x-wc-webhook-signature": woo_valid_sig}, payload, secret) is True
    assert woo_conn.verify_webhook({"x-wc-webhook-signature": "bad_woo_sig=="}, payload, secret) is False
    result.record_pass("WooCommerce webhook HMAC signature check")


async def test_connector_edge_cases_and_error_handling():
    print("\n--- 7. Testing Connector Edge Cases, Missing Credentials & Error Mapping ---")
    
    # 1. Missing / Empty Credentials
    connectors_with_auth = [
        ("Amazon fetch_catalog", AmazonConnector().fetch_catalog({})),
        ("Amazon push_product", AmazonConnector().push_product({}, {"sku": "TEST"})),
        ("Amazon update_stock", AmazonConnector().update_stock({}, "TEST", 10)),
        ("Etsy fetch_catalog", EtsyConnector().fetch_catalog({})),
        ("Etsy push_product", EtsyConnector().push_product({}, {"sku": "TEST"})),
        ("Etsy update_stock", EtsyConnector().update_stock({}, "TEST", 10)),
        ("TikTok fetch_catalog", TikTokShopConnector().fetch_catalog({})),
        ("TikTok push_product", TikTokShopConnector().push_product({}, {"sku": "TEST"})),
        ("TikTok update_stock", TikTokShopConnector().update_stock({}, "TEST", 10)),
        ("eBay fetch_catalog", EBayConnector().fetch_catalog({})),
        ("eBay push_product", EBayConnector().push_product({}, {"sku": "TEST"})),
        ("eBay update_stock", EBayConnector().update_stock({}, "TEST", 10)),
    ]

    for name, coro in connectors_with_auth:
        try:
            await coro
            result.record_fail(f"{name} empty credentials", "Expected ConnectorAuthError but succeeded")
        except ConnectorAuthError:
            result.record_pass(f"{name} raised ConnectorAuthError on missing credentials")
        except Exception as exc:
            result.record_fail(f"{name} empty credentials", f"Unexpected exception: {type(exc).__name__}: {exc}")

    # 2. Missing SKU in push_product
    try:
        await AmazonConnector().push_product({"access_token": "token123"}, {"title": "No SKU Item"})
        result.record_fail("Amazon push_product missing SKU", "Expected ConnectorValidationError")
    except ConnectorValidationError:
        result.record_pass("Amazon push_product raises ConnectorValidationError when SKU is empty")

    try:
        await EBayConnector().push_product({"access_token": "token123"}, {"title": "No SKU Item"})
        result.record_fail("eBay push_product missing SKU", "Expected ConnectorValidationError")
    except ConnectorValidationError:
        result.record_pass("eBay push_product raises ConnectorValidationError when SKU is empty")

    # 3. HTTP Error Mapping via _handle_http_errors
    try:
        _handle_http_errors(401, "Unauthorized", "Shopify")
        result.record_fail("401 handler", "Expected ConnectorAuthError")
    except ConnectorAuthError:
        result.record_pass("HTTP 401 mapped to ConnectorAuthError")

    try:
        _handle_http_errors(403, "Forbidden", "Amazon")
        result.record_fail("403 handler", "Expected ConnectorAuthError")
    except ConnectorAuthError:
        result.record_pass("HTTP 403 mapped to ConnectorAuthError")

    try:
        _handle_http_errors(429, "Too Many Requests", "TikTok")
        result.record_fail("429 handler", "Expected ConnectorRateLimitError")
    except ConnectorRateLimitError as exc:
        if exc.retry_after_seconds == 60.0:
            result.record_pass("HTTP 429 mapped to ConnectorRateLimitError with default retry_after_seconds")
        else:
            result.record_fail("429 retry_after", f"Unexpected retry_after_seconds: {exc.retry_after_seconds}")

    try:
        _handle_http_errors(422, "Unprocessable Entity", "Etsy")
        result.record_fail("422 handler", "Expected ConnectorValidationError")
    except ConnectorValidationError:
        result.record_pass("HTTP 422 mapped to ConnectorValidationError")

    try:
        _handle_http_errors(503, "Service Unavailable", "eBay")
        result.record_fail("503 handler", "Expected ConnectorNetworkError")
    except ConnectorNetworkError:
        result.record_pass("HTTP 503 mapped to ConnectorNetworkError")


def test_zero_emoji_invariant():
    print("\n--- 8. Testing Zero-Emoji Invariant across Server Codebase ---")
    emoji_pattern = re.compile(
        r"[\U0001F600-\U0001F64F"  # emoticons
        r"\U0001F300-\U0001F5FF"  # symbols & pictographs
        r"\U0001F680-\U0001F6FF"  # transport & map symbols
        r"\U0001F1E0-\U0001F1FF"  # flags (iOS)
        r"\U0001F900-\U0001F9FF"  # supplemental symbols
        r"\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-a
        r"\U00002702-\U000027B0"  # dingbats
        r"\U000024C2-\U0001F251"
        r"\U00002600-\U000026FF"  # miscellaneous symbols
        r"\U00002B50"              # star
        r"\U0000FE0F"              # variation selector-16
        r"\ufffd"                  # replacement character
        r"]+",
        flags=re.UNICODE,
    )
    
    server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "server"))
    found_emojis = []
    for root, _, files in os.walk(server_dir):
        for file in files:
            if file.endswith((".py", ".json", ".html", ".js", ".css")):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    matches = emoji_pattern.findall(content)
                    if matches:
                        found_emojis.append((filepath, matches))

    if len(found_emojis) == 0:
        result.record_pass("Zero-Emoji invariant verified across all server files (0 violations)")
    else:
        result.record_fail("Zero-Emoji check", f"Found emojis: {found_emojis}")


def test_flake8_ast_syntax_check():
    print("\n--- 9. Testing AST Syntax & Compilation across Server Codebase ---")
    import ast
    server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "server"))
    py_files = [os.path.join(root, f) for root, _, files in os.walk(server_dir) for f in files if f.endswith(".py")]
    
    for fpath in py_files:
        rel = os.path.relpath(fpath, server_dir)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                source = f.read()
            ast.parse(source, filename=fpath)
            result.record_pass(f"AST compilation valid: server/{rel}")
        except Exception as exc:
            result.record_fail(f"AST compilation error: server/{rel}", str(exc))


async def main():
    print("=================================================================")
    print("  KopyKat Milestone 2 Empirical Verification & Challenge Suite  ")
    print("=================================================================")
    test_restricted_cidr_ranges()
    test_hostname_resolution_and_dns_rebinding()
    await test_redirect_rejection_async()
    await test_streaming_response_size_limits()
    await test_socket_pinning()
    test_platform_webhook_hmac_signatures()
    await test_connector_edge_cases_and_error_handling()
    test_zero_emoji_invariant()
    test_flake8_ast_syntax_check()

    print("\n=================================================================")
    print(f"  Summary: {result.passed} PASSED, {result.failed} FAILED")
    print("=================================================================")
    if result.failed > 0:
        print("\nFailures:")
        for err in result.errors:
            print(f"  - {err}")
        return 1
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
