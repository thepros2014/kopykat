# Dispatch History

## 2026-08-23T10:17:39Z
You are the Sub-Orchestrator for Milestone 2 (Autonomous Connectors, Real-Time Sync & Async SSRF Defense).
Your Working Directory: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m2
Original Request Path: c:\Users\plumb\Desktop\claude-project\.agents\ORIGINAL_REQUEST.md
PROJECT.md Path: c:\Users\plumb\Desktop\claude-project\PROJECT.md
Project Root: c:\Users\plumb\Desktop\claude-project

Scope: Milestone 2 (Features F7, F8, F9, F10)
Write Ownership: `server/connector_engine.py`, `server/connector_registry.py`, `server/integrations.py`, `server/inventory.py`, `tests/test_connectors.py`, `tests/test_inventory.py`, `tests/test_ssrf_async.py`.

Tasks:
1. Read `ORIGINAL_REQUEST.md` and `PROJECT.md § Milestones / M2`.
2. Implement and verify the Autonomous Connectors, Real-Time Sync, and Async SSRF/DNS Rebinding Protections:
   - Build hardened non-blocking `SafeAsyncHTTPClient` using `httpx.AsyncClient`:
     - Resolves hostname via DNS once, validates IP against all RFC 1918, RFC 3927, loopback, multicast, and reserved ranges.
     - Directs socket connection to pre-validated IP to eliminate TOCTOU DNS rebinding.
     - Preserves SNI/Host header for TLS verification.
     - Blocks redirects (`follow_redirects=False`).
     - Caps streaming response bodies at 2 MB max.
   - Standardize `PlatformConnector` architecture and implement async connectors for Amazon, Shopify, Etsy, TikTok Shop, and eBay in `server/integrations.py`.
   - Implement bi-directional inventory & product catalog sync with async loop-free fanout in `server/inventory.py`. Support `{"shopify", "amazon", "etsy", "tiktok", "ebay", "walmart", "temu", "woocommerce"}`.
   - Enforce webhook idempotency on `(platform, event_id)` with `InventoryWebhookEvent`.
3. Dispatch Worker -> Reviewer -> Challenger -> Auditor cycle to implement and rigorously verify M2.
   MANDATORY INTEGRITY WARNING: DO NOT CHEAT. All implementations must be genuine. Zero-emoji policy strictly enforced.
4. Verify: `python -m pytest tests/ -v`, `python -m flake8 server --count --select=E9,F63,F7,F82`, and `python tests/test_no_emojis.py`.
5. Write `handoff.md` and report back to parent.
