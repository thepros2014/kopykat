# Scope: Milestone 4 (Security Governance, Financial Invariants & Frontend UI Integration)

## Architecture & Boundaries
Milestone 4 integrates and finalizes:
1. Frontend UI/UX Integration:
   - `frontend/dashboard.html`: Complete `<section>` markup blocks matching JS handlers for:
     - `section-miner` (Competitor Review Miner)
     - `section-inventory` (Multi-Channel Inventory Balancer)
     - `section-ugc` (Customer Reviews & UGC Drips)
     - `section-pricing-monitor` (Margin & Price Monitor)
     - `section-leads` (Social Opportunity Leads / Reddit Scout)
     - `section-growth` (Growth Analytics & SEO)
     - `section-brand-persona` (Brand Persona Configuration)
     - `section-listing-optimizer` (Marketplace Listing Optimizer for Amazon, Shopify, Etsy, TikTok Shop, eBay)
     - `section-addons-store` (Add-Ons Store)
   - `frontend/admin.html`: Connect to `/admin/mrr-metrics` and display MRR, ARR, subscriber tier breakdown, valuation estimates, telemetry stats.
2. Financial Invariants & Quota Ledger:
   - Dual-bucket quota reservation (`reserve_user_generations` prioritizing monthly then purchased quota).
   - Atomic refund (`refund_user_generations`) on upstream/generation failures.
   - HTTP 503 on unconfigured Stripe gateway.
   - BYOK custom AI keys restricted strictly to Megastore tier.
3. Security Governance & Modernization:
   - Multi-tenant data scoping (`user_id == user.id`).
   - Fernet credential encryption for marketplace API keys/tokens and BYOK keys.
   - Bcrypt max 72 UTF-8 bytes limit.
   - Zero-emoji policy strictly maintained across all HTML, JS, CSS, and Python code.
   - Pydantic v2 `ConfigDict` modernizations in `server/models.py`.
   - Comprehensive test suite in `tests/test_frontend_admin_m4.py`.

## Feature Inventory (M4 Features)
| # | Feature | Description | Milestone | Status |
|---|---------|-------------|-----------|--------|
| F15 | Frontend Dashboard Complete Sections | All 9 dashboard sections wired with clean UI markup matching JS functions | M4 | DONE |
| F16 | Frontend Admin MRR & Telemetry UI | Admin metrics dashboard fetching and displaying MRR/ARR/tiers/telemetry | M4 | DONE |
| F17 | Dual-Bucket Quota & Atomic Refund | Monthly first, purchased second; atomic refund on generation failure | M4 | DONE |
| F18 | Security Governance & Scoping | Multi-tenant isolation, Fernet encryption, bcrypt 72-byte limit, BYOK Megastore gating | M4 | DONE |
| F19 | Pydantic v2 & M4 Test Suite | Modernized ConfigDict, clean linting, comprehensive M4 test coverage | M4 | DONE |

## Write Ownership
- `frontend/dashboard.html`
- `frontend/admin.html`
- `server/main.py`
- `server/models.py`
- `tests/test_frontend_admin_m4.py`
