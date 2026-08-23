## 2026-08-23T13:10:38Z
You are the Implementation Worker (worker_m2_2) for Milestone 2 (Autonomous Connectors, Real-Time Sync & Async SSRF Defense).
Your working directory: c:\Users\plumb\Desktop\claude-project\.agents\worker_m2_2\
Original Request: c:\Users\plumb\Desktop\claude-project\.agents\ORIGINAL_REQUEST.md
PROJECT.md: c:\Users\plumb\Desktop\claude-project\PROJECT.md
SCOPE.md: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m2\SCOPE.md
Project Root: c:\Users\plumb\Desktop\claude-project

Explorer Reports:
- Explorer 1 (SSRF & Connector Engine): `c:\Users\plumb\Desktop\claude-project\.agents\explorer_m2_1\analysis.md` and `handoff.md`
- Explorer 2 (Platform Connectors): `c:\Users\plumb\Desktop\claude-project\.agents\explorer_m2_2\analysis.md` and `handoff.md`
- Explorer 3 (Inventory Sync & Idempotency): `c:\Users\plumb\Desktop\claude-project\.agents\explorer_m2_3\analysis.md` and `handoff.md`

Your Write Ownership:
- `server/connector_engine.py`
- `server/connector_registry.py`
- `server/integrations.py`
- `server/inventory.py`
- `tests/test_connectors.py`
- `tests/test_inventory.py`
- `tests/test_ssrf_async.py`

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Zero-Emoji Policy: STRICTLY ENFORCED. No emojis or non-ASCII emoji characters anywhere in code, docstrings, comments, or output.

Detailed Implementation Requirements:
1. `server/connector_engine.py`:
   - Implement `SafePinningNetworkBackend` (subclassing `httpcore.AnyIOBackend` or custom transport) and `SafeAsyncHTTPClient`.
   - Comprehensive IP filtering: check IPv4 & IPv6 addresses against loopback (`127.0.0.0/8`, `::1`), private RFC 1918 (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local RFC 3927 (`169.254.0.0/16` including `169.254.169.254`), CGNAT (`100.64.0.0/10`), reserved (`240.0.0.0/4`, `0.0.0.0/8`), multicast (`224.0.0.0/4`, `ff00::/8`), documentation ranges (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`, `2001:db8::/32`), IPv6 ULA (`fc00::/7`), IPv6 link-local (`fe80::/10`), and IPv4-mapped IPv6 (`::ffff:0:0/96`).
   - Eliminate TOCTOU DNS rebinding: resolve hostname via DNS once, validate IP, and pin socket connection directly to the validated IP while preserving SNI and HTTP Host header for TLS / virtual hosting.
   - Redirect rejection: `follow_redirects=False` and raise `SSRFError` on 3xx responses.
   - Streaming response body capping: enforce max size of 2,000,000 bytes (2 MB), raising `SSRFError` if exceeded.
   - Preserve existing synchronous functions (`validate_public_url`, `fetch_api_document`, `build_connector_spec`, `discover_connector`, etc.) for backwards compatibility.

2. `server/connector_registry.py`:
   - Implement async connector execution (`async_execute_operation` / `execute_operation`) utilizing `SafeAsyncHTTPClient`.

3. `server/integrations.py`:
   - Standardize `PlatformConnector` protocol:
     - `platform_name: str`
     - `async def fetch_catalog(self, credentials: dict, limit: int = 50) -> list[dict]`
     - `async def push_product(self, credentials: dict, product_data: dict) -> dict`
     - `async def update_stock(self, credentials: dict, sku: str, quantity: int) -> dict`
     - `def verify_webhook(self, headers: dict, raw_payload: bytes, secret: str) -> bool`
   - Concrete implementations: `AmazonConnector`, `ShopifyConnector`, `EtsyConnector`, `TikTokShopConnector`, `EBayConnector`.
   - `CONNECTOR_REGISTRY` and `get_connector(platform: str) -> Optional[PlatformConnector]`.
   - Custom exceptions: `ConnectorAuthError`, `ConnectorRateLimitError`, `ConnectorNetworkError`, `ConnectorValidationError`.
   - Maintain legacy push methods (`push_to_wordpress`, `push_to_mailchimp`, `push_to_hubspot`, `push_to_shopify`, `push_to_webflow`, `background_push`) for backward compatibility.

4. `server/inventory.py`:
   - Expand `SUPPORTED_INVENTORY_PLATFORMS` to include `{"shopify", "amazon", "etsy", "tiktok", "ebay", "walmart", "temu", "woocommerce"}`.
   - Platform alias normalization (`tiktok_shop` -> `tiktok`, `woo` -> `woocommerce`).
   - Loop-free fanout (ignoring originating platform and avoiding circular updates).
   - Drift reconciliation (`reconcile_inventory_sku`).
   - Webhook idempotency ledger with `InventoryWebhookEvent` on `(platform, event_id)` preventing replay stock debits.

5. Test Suites:
   - `tests/test_ssrf_async.py`: Test SSRF defenses, private IP rejections, DNS rebinding elimination, redirect blocking, 2MB size capping.
   - `tests/test_connectors.py`: Test `PlatformConnector` implementations, methods, webhook verification, registry.
   - `tests/test_inventory.py`: Test multi-platform fanout across all 8 platforms, loop-free suppression, drift reconciliation, webhook idempotency.

6. Verification:
   - Run `python -m pytest tests/ -v` (all tests must pass 100%).
   - Run `python -m flake8 server --count --select=E9,F63,F7,F82` (0 errors).
   - Run `python tests/test_no_emojis.py` (0 emojis).

Write `c:\Users\plumb\Desktop\claude-project\.agents\worker_m2_2\handoff.md` and notify parent when complete with verification output.
