# Handoff Report — Explorer 3 (Security & Test Invariants Survey)

**Agent**: Explorer 3 (Security & Test Invariants Survey)  
**Date**: 2026-08-23T10:16:30Z  
**Type**: Hard (Task Complete)  
**Working Directory**: `c:\Users\plumb\Desktop\claude-project\.agents\explorer_survey_3`  

---

## 1. Observation

Direct observations and citations from the codebase:

1. **Authentication & Cryptography**:
   - `server/auth.py:40-42`: Password length strictly capped at 72 bytes (`len(pwd_bytes) > 72` raises HTTP 400), using Bcrypt for hashing.
   - `server/auth.py:112-145`: `get_current_user_apikey` handles both JWT sessions and SHA-256 hashed API keys (`sc_...`), validating `is_active`, updating `last_used`, and incrementing `requests_today`.
   - `server/auth.py:207-226`: Fernet encryption is used for all stored marketplace and custom connector credentials.
   - `server/models.py` & `server/main.py:184-297`: Email verification and password reset utilize SHA-256 hashed single-use tokens stored in `VerificationToken`.

2. **Tenant Isolation & IDOR Protections**:
   - `server/main.py:681,697,720,754,816`: All connector operations filter strictly by `user_id == user.id`.
   - `server/main.py:936,960` & `server/inventory.py:51,154`: Inventory management operations filter by `user_id == user.id`.
   - `server/main.py:1144,1167,1205`: Price and margin items filter by `user_id == user.id`.
   - `server/main.py:1091,1123`: Customer review submissions and retrieval filter by `user_id == user.id`.
   - `server/main.py:1367,1387`: Brand personas strictly scoped by unique `user_id`.
   - `tests/test_adversarial_hardening.py:217-248`: Cross-tenant IDOR attack simulation passes with HTTP 404.

3. **Subscription Entitlements & BYOK Gating**:
   - `server/billing.py:22-80`: Four canonical plans (`free`, `boutique`, `standard`, `megastore`) and four à-la-carte add-ons (`brand_voice_training`, `marketplace_optimizer_pack`, `done_for_you_marketing_pack`, `bulk_catalog_import_pass`).
   - `server/billing.py:427-440`: `user_has_entitlement` validates paid plan membership (`boutique`, `standard`, `megastore`) or active `UserEntitlement` record. Free users without explicit entitlement receive HTTP 403 (`server/main.py:1385,1427`).
   - `server/main.py:912-914`: Custom AI API key (BYOK) endpoint requires `user.plan == "megastore"`, returning HTTP 403 for other tiers.

4. **Financial Invariants & Ledger Handling**:
   - `server/main.py:320-356`: `reserve_user_generations` prioritizes `monthly_generations` bucket over `purchased_generations`, uses `with_for_update()` row locking, and raises HTTP 402 if balance is insufficient.
   - `server/main.py:358-365`: `refund_user_generations` restores reserved quota to respective buckets upon upstream failure.
   - `server/main.py:619,852`: Direct raw SQL balance update is used in `/api/campaign/generate-vision` and `/api/competitor/mine-reviews` rather than calling `reserve_user_generations`.
   - `server/billing.py:140-156,194-196` & `server/main.py:1487-1489`: Missing Stripe API keys or Price IDs raise HTTP 503 Service Unavailable.
   - `server/billing.py:206-211` & `server/inventory.py:32-46`: Stripe webhooks and inventory webhooks enforce idempotency via `StripeEvent.event_id` and `InventoryWebhookEvent(platform, event_id)`.
   - `tests/test_adversarial_hardening.py:9-146`: Purchased generations survive subscription renewals, upgrades, and cancellations without double-counting.

5. **SSRF, DNS Rebinding & Content Governance**:
   - `server/connector_engine.py:27-45`: `validate_public_url` enforces HTTPS, rejects localhost, performs DNS resolution, and rejects private/loopback/link-local/multicast IP ranges. Redirects are disabled (`allow_redirects=False`).
   - `server/content_governance.py:18-52`: `audit_generated_content` cleans defamatory terms and unsubstantiated absolute claims.

6. **Test Suite Baseline & Tool Execution**:
   - `python -m pytest tests/ -v`: Ran all 65 tests in 20 test files — **65 passed, 0 failed, 7 warnings**.
   - `python -m flake8 server --count --select=E9,F63,F7,F82`: **0 errors**.
   - `tests/test_no_emojis.py`: **0 emojis found** across `server/` and `frontend/`.

---

## 2. Logic Chain

1. **Premise**: Enterprise expansion requires strict multi-tenant isolation, tamper-proof financial accounting, SSRF/DNS rebinding prevention, and zero-emoji compliance.
2. **Analysis**:
   - Tenant isolation is consistently enforced at the ORM query level across all endpoints using authenticated `user.id`.
   - The dual-bucket balance model (`monthly_generations` + `purchased_generations`) correctly prevents purchased credits from being wiped during subscription cycles or plan cancellations.
   - Idempotency mechanisms in Stripe and inventory webhooks prevent replay attacks and double debiting.
   - Direct raw SQL balance updates in `/api/campaign/generate-vision` and `/api/competitor/mine-reviews` represent a minor architectural inconsistency that should be unified under `reserve_user_generations`.
   - SSRF and DNS rebinding protections in `validate_public_url` meet enterprise standards by verifying resolved IP addresses before establishing connections and prohibiting HTTP redirects.
   - The test suite of 65 unit/integration tests provides high coverage of adversarial scenarios, authentication flows, and monetization features.
3. **Deduction**: The core platform architecture is secure and ready for multi-modal expansion, with specific recommendations for ledger unification and test script runner improvements.

---

## 3. Caveats

- Database tests run against SQLite in-memory DB (`sqlite:///:memory:`) where `with_for_update()` is a no-op; pessimistic locking logic is active for PostgreSQL production deployments.
- `tests/test_no_emojis.py` scans `server/` and `frontend/` files; markdown documentation and root utility files should also maintain emoji discipline.
- Deprecation warnings from Pydantic v1 `class Config` and FastAPI `@app.on_event` do not affect test execution but should be modernized during subsequent refactorings.

---

## 4. Conclusion

- All baseline acceptance criteria are satisfied:
  - Pytest: 65/65 tests pass.
  - Flake8: 0 critical errors.
  - Emoji audit: 0 emojis in codebase.
- Security governance, tenant isolation, and financial invariants are well-defined and enforced.
- Key enhancement identified: Standardize vision and competitor mining endpoints to use the centralized dual-bucket `reserve_user_generations` / `refund_user_generations` helper.

---

## 5. Verification Method

To independently reproduce and verify this assessment:

1. Run the test suite:
   ```powershell
   python -m pytest tests/ -v
   ```
   *Expected result*: 65 passed, 0 failed.

2. Run flake8 syntax and undefined variable check:
   ```powershell
   python -m flake8 server --count --select=E9,F63,F7,F82
   ```
   *Expected result*: Output is `0` with exit code 0.

3. Run zero-emoji regression test:
   ```powershell
   python -m pytest tests/test_no_emojis.py -v
   ```
   *Expected result*: 1 passed.

4. Inspect detailed survey findings:
   - File: `c:\Users\plumb\Desktop\claude-project\.agents\explorer_survey_3\analysis.md`
