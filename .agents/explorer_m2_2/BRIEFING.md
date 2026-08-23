# BRIEFING — 2026-08-23T10:18:12Z

## Mission
Analyze existing integration connectors in `server/integrations.py` and across codebase, and design standardized `PlatformConnector` architecture and implementations for Amazon, Shopify, Etsy, TikTok Shop, eBay with SafeAsyncHTTPClient, Fernet credential decryption, rate limiting, error handling, webhook verification, zero-emoji invariant, and flake8 compliance.

## 🔒 My Identity
- Archetype: Explorer
- Roles: Investigation, Synthesis, Architecture Design
- Working directory: c:\Users\plumb\Desktop\claude-project\.agents\explorer_m2_2\
- Original parent: 6802dd3f-cb03-4ab5-9264-611411534138
- Milestone: Milestone 2 (Autonomous Connectors, Real-Time Sync & Async SSRF Defense)

## 🔒 Key Constraints
- Read-only investigation — do NOT modify source code files in the repo (only write reports in `.agents/explorer_m2_2/`)
- Zero-emoji invariant across all codebase / reports
- Flake8 compliance (E501 <= 120 chars, no unused imports, etc.)
- Strict typing, async/await compatibility, SafeAsyncHTTPClient integration, Fernet encryption/decryption handling

## Current Parent
- Conversation ID: 6802dd3f-cb03-4ab5-9264-611411534138
- Updated: 2026-08-23T10:18:12Z

## Investigation State
- **Explored paths**: `server/integrations.py`, `PROJECT.md`, `SCOPE.md`, `ORIGINAL_REQUEST.md`, `server/shopify_import.py`, `server/inventory.py`, `server/database.py`, `server/auth.py`, `tests/test_connectors.py`, `tests/test_inventory.py`, `tests/test_no_emojis.py`
- **Key findings**:
  - `server/integrations.py` currently has stub functions raising `NotImplementedError` for Amazon, eBay, Walmart, Temu and synchronous requests for WordPress, Mailchimp, HubSpot, Shopify, Webflow.
  - Standardized `PlatformConnector` Protocol contract defined with `fetch_catalog`, `push_product`, `update_stock`, `verify_webhook`.
  - Concrete async connector specifications designed for Amazon (SP-API), Shopify (Admin API), Etsy (v3 API), TikTok Shop (Open API), and eBay (Inventory API).
  - Integration with `SafeAsyncHTTPClient` ensures SSRF prevention, IP pre-validation, socket pinning, SNI preservation, redirect blocking, and 2MB payload streaming cap.
  - Webhook verification supports HMAC-SHA256 (Shopify, Amazon, Etsy, TikTok, eBay) with `hmac.compare_digest`.
  - Stored credentials in `UserIntegration` remain encrypted with Fernet and decrypted dynamically in-memory.
- **Unexplored areas**: None within Explorer 2 scope.

## Key Decisions Made
- Preserved backwards compatibility for existing synchronous push functions and `background_push` in `server/integrations.py`.
- Formulated custom connector exception hierarchy (`ConnectorAuthError`, `ConnectorRateLimitError`, `ConnectorNetworkError`, `ConnectorValidationError`).
- Documented full implementation blueprints in `analysis.md` and `handoff.md`.

## Artifact Index
- `.agents/explorer_m2_2/DISPATCH.md` — Incoming task records
- `.agents/explorer_m2_2/BRIEFING.md` — Working memory
- `.agents/explorer_m2_2/progress.md` — Progress tracker
- `.agents/explorer_m2_2/analysis.md` — Detailed analysis
- `.agents/explorer_m2_2/handoff.md` — Handoff report
