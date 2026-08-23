## 2026-08-23T13:30:30Z

<USER_REQUEST>
You are the Sub-Orchestrator for Milestone 4 (Security Governance, Financial Invariants & Frontend UI Integration).
Your Working Directory: c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m4
Original Request Path: c:\Users\plumb\Desktop\claude-project\.agents\ORIGINAL_REQUEST.md
PROJECT.md Path: c:\Users\plumb\Desktop\claude-project\PROJECT.md
TEST_READY.md Path: c:\Users\plumb\Desktop\claude-project\TEST_READY.md
Project Root: c:\Users\plumb\Desktop\claude-project

Scope: Milestone 4 (Features F15, F16, F17, F18, F19)
Write Ownership: `frontend/dashboard.html`, `frontend/admin.html`, `server/main.py` (financial reservation / auth / lifespan cleanups), `server/models.py` (Pydantic v2 ConfigDict), `tests/test_frontend_admin_m4.py`.

Tasks:
1. Read `ORIGINAL_REQUEST.md` and `PROJECT.md § Milestones / M4`.
2. Implement and verify the Security Governance, Financial Invariants, and Frontend UI Integration:
   - Frontend UI/UX Integration:
     - In `frontend/dashboard.html`: Implement complete, clean `<section>` markup blocks matching existing JavaScript handlers for:
       - `section-miner` (Competitor Review Miner)
       - `section-inventory` (Multi-Channel Inventory Balancer)
       - `section-ugc` (Customer Reviews & UGC Drips)
       - `section-pricing-monitor` (Margin & Price Monitor)
       - `section-leads` (Social Opportunity Leads / Reddit Scout)
       - `section-growth` (Growth Analytics & SEO)
       - `section-brand-persona` (Brand Persona Configuration)
       - `section-listing-optimizer` (Marketplace Listing Optimizer for Amazon, Shopify, Etsy, TikTok Shop, eBay)
       - `section-addons-store` (Add-Ons Store)
     - In `frontend/admin.html`: Connect to `/admin/mrr-metrics` and display MRR, ARR, subscriber tier breakdown, valuation estimates, and telemetry stats.
   - Financial Invariants & Quota Ledger:
     - Verify centralized dual-bucket `reserve_user_generations` (monthly prioritized before purchased quota) and atomic `refund_user_generations` on upstream errors across all generation routes.
     - Verify HTTP 503 on unconfigured Stripe gateway.
     - Verify BYOK custom AI keys restricted strictly to Megastore tier.
   - Security Governance:
     - Multi-tenant data scoping (`user_id == user.id`), Fernet credential encryption, bcrypt max 72 UTF-8 bytes limit.
     - Zero-emoji policy strictly maintained across all HTML, JS, CSS, and Python code.
     - Pydantic v2 ConfigDict modernizations in `server/models.py`.
3. Dispatch Worker -> Reviewer -> Challenger -> Auditor cycle to implement and rigorously verify M4.
   MANDATORY INTEGRITY WARNING: DO NOT CHEAT. All implementations must be genuine. Zero-emoji policy strictly enforced.
4. Verify: `python -m pytest tests/ -v`, `python -m flake8 server --count --select=E9,F63,F7,F82`, and `python tests/test_no_emojis.py`.
5. Write `handoff.md` and report back to parent.
</USER_REQUEST>

## 2026-08-23T18:10:31Z

**Context**: Milestone 4 Gate Remediation
**Content**: Reviewer 2 identified 3 specific items to fix:
1. In `tests/test_frontend_admin_m4.py` lines 52-53: Add `type="subscription"` to `RevenueRecord` instantiation (`RevenueRecord(id="rev-1", user_id=user_bq.id, amount_cents=17949, type="subscription", status="succeeded")`).
2. In `tests/test_frontend_admin_m4.py` line 368: Correct regex unicode escapes to 8-character escapes `\U0001F300-\U0001F5FF` etc., matching `tests/test_no_emojis.py`.
3. In `server/main.py` error handlers: Ensure `/api/competitor/mine-reviews` and generation routes return JSON responses (e.g. `JSONResponse(status_code=500, content={"detail": ...})` or standard HTTPException) when catching upstream exceptions.
4. Also check `tests/test_e2e_enterprise.py` and `tests/test_e2e_tiers.py` to ensure all tests in `tests/` pass 100%.

Please dispatch a worker to apply these fixes, re-verify with reviewers/auditor, and report the final handoff.
**Action**: Remediate M4 review feedback and achieve 100% pytest pass.
