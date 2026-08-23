# Scope: Milestone 2 (Autonomous Connectors, Real-Time Sync & Async SSRF Defense)

## Architecture
- `server/connector_engine.py`: SafeAsyncHTTPClient, IP pre-validation (RFC 1918, RFC 3927, loopback, multicast, reserved), socket pinning via `SafePinningNetworkBackend` (httpcore.AnyIOBackend subclass), SNI preservation, redirect blocking (follow_redirects=False), 2MB streaming cap, OpenAPI spec discovery.
- `server/connector_registry.py`: Async connector execution runtime with IP-pinned transport.
- `server/integrations.py`: Standardized `PlatformConnector` protocol and concrete async connectors for Amazon, Shopify, Etsy, TikTok Shop, eBay, Walmart, Temu, and WooCommerce (`fetch_catalog`, `push_product`, `update_stock`, `verify_webhook`).
- `server/inventory.py`: Bi-directional inventory & product catalog sync with async loop-free fanout across supported platforms (`{"shopify", "amazon", "etsy", "tiktok", "ebay", "walmart", "temu", "woocommerce"}`), drift reconciliation, webhook idempotency ledger via `InventoryWebhookEvent` on `(platform, event_id)`.
- `tests/test_connectors.py`, `tests/test_inventory.py`, `tests/test_ssrf_async.py`: Comprehensive test suites verifying connectors, inventory fanout, webhook idempotency, and SSRF/DNS rebinding defense.

## Feature Inventory
| # | Feature | Description | Milestone | Status |
|---|---------|-------------|-----------|--------|
| F7 | Autonomous Platform Connectors | Standardized async connector clients for Amazon, Shopify, Etsy, TikTok Shop, eBay, Walmart, Temu, WooCommerce | M2 | DONE |
| F8 | Real-Time Sync & Fanout Engine | Bi-directional inventory & product catalog sync, loop-free fanout, stock drift reconciliation across supported platforms | M2 | DONE |
| F9 | Webhook Idempotency Ledger | Idempotent webhook processing on unique `(platform, event_id)` preventing replay stock debits | M2 | DONE |
| F10 | Non-Blocking Async HTTP & SSRF Defense | SafeAsyncHTTPClient with IP pre-resolution, socket pinning, SNI preservation, redirect blocking, 2MB streaming cap | M2 | DONE |

## Write Ownership
- `server/connector_engine.py`
- `server/connector_registry.py`
- `server/integrations.py`
- `server/inventory.py`
- `tests/test_connectors.py`
- `tests/test_inventory.py`
- `tests/test_ssrf_async.py`

## Gate Status
- **PASS**: Approved by Reviewer 1, Reviewer 2, Challenger 1, Challenger 2, and CLEAN audit verdict from Forensic Auditor.
