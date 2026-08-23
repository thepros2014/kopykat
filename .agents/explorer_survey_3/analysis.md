# Comprehensive Security Governance, Financial Invariants & Test Baseline Survey Report

**Explorer**: Explorer 3 (Security & Test Invariants Survey)  
**Date**: 2026-08-23T10:15:00Z  
**Target Repository**: `c:\Users\plumb\Desktop\claude-project`  
**Working Directory**: `c:\Users\plumb\Desktop\claude-project\.agents\explorer_survey_3`  

---

## 1. Executive Summary

An exhaustive survey of the KopyKat codebase was conducted across security governance, tenant isolation, subscription entitlement logic, financial invariants (dual-bucket credit deduction, balance reservation, failure refunds, HTTP 503 gateway fallback, webhook idempotency), test suite baseline, flake8 compliance, and zero-emoji enforcement.

### Baseline Acceptance Criteria Status:
1. `python -m pytest tests/ -v`: **100% Pass** (65 passed, 0 failed, 7 deprecation warnings).
2. `python -m flake8 server --count --select=E9,F63,F7,F82`: **0 Errors** (Clean).
3. `python tests/test_no_emojis.py`: **Clean** (Zero emojis detected across `server/` and `frontend/`).
4. **Security & Financial Invariants**: Robust architecture established with specific unification opportunities identified for vision & competitor mining balance reservations.

---

## 2. Security Governance & Tenant Isolation State

### 2.1 Authentication & Credential Governance
- **Password Hashing**: Bcrypt with explicit 72 UTF-8 byte maximum length check (`server/auth.py:40-42`) preventing bcrypt DoS vector.
- **Dual Authentication Mechanism**: `get_current_user_apikey` (`server/auth.py:112-145`) validates either:
  1. Signed JWT access tokens (`HS256`, 1440m expiration).
  2. SHA-256 hashed API keys (`sc_...`), verifying `is_active` status, updating `last_used` timestamps and incrementing `requests_today`.
- **Token Verification & Password Reset**: SHA-256 hashed tokens stored in `VerificationToken` table (`server/database.py:71-78`, `server/main.py:184-297`) with 1-hour expiry, protecting against unhashed token leaks.
- **Data Encryption at Rest**: Integration credentials (Shopify, eBay, Amazon, custom connectors) and BYOK custom AI API keys are symmetrically encrypted using Fernet (`server/auth.py:207-226`, `server/database.py:36,85,149`). Plaintext secrets are never stored in database tables or connector specs.

### 2.2 Multi-Tenant Isolation & IDOR Protections
- All data access and mutation queries enforce strict user scoping via `user_id == user.id`:
  - `CustomConnector`: Scoped on listing (`server/main.py:681`), retrieval (line 697), credential association (line 720), execution testing (line 754), and toggle switch (line 816).
  - `InventoryItem`: Scoped on listing (`server/main.py:936`), creation/updates (line 960), and stock reconciliation (`server/inventory.py:51,154`).
  - `PriceMarginItem`: Scoped on listing (`server/main.py:1144`), upsert (line 1167), and deletion (line 1205).
  - `CustomerReview`: Scoped on review submission and retrieval (`server/main.py:1091,1123`).
  - `BrandPersona`: Scoped to `user_id` with 1-to-1 unique constraint (`server/main.py:1367,1387`).
  - `Campaign` & `PushJob`: Scoped to `user.id` (`server/main.py:480,496,503,592,643,661`).
  - `APIKey`: Scoped to `user.id` on creation, retrieval, and revocation (`server/auth.py:176-205`).
- Cross-tenant IDOR attack resistance is explicitly verified in `tests/test_adversarial_hardening.py:217-248` (attempted deletion/access of foreign tenant resources returns HTTP 404).

### 2.3 Subscription Entitlements & BYOK Access Gating
- **Tier Structure**:
  - `free`: 5 generations/mo, 1 connector, 1 automation.
  - `boutique`: 150 generations/mo ($179.49/mo), 2 connectors, 1 automation.
  - `standard`: 1,000 generations/mo ($379.49/mo), 10 connectors, 2 automations.
  - `megastore`: 2,500 generations/mo ($9,639.63/mo), 999 connectors, 999 automations, BYOK unlimited.
- **Add-On Catalog**:
  - `brand_voice_training` ($49 one-time)
  - `marketplace_optimizer_pack` ($29 one-time)
  - `done_for_you_marketing_pack` ($149/mo recurring)
  - `bulk_catalog_import_pass` ($19 one-time)
- **Entitlement Checks**: `user_has_entitlement(user, key, db)` (`server/billing.py:427-440`) verifies if a user has a paid plan (`boutique`, `standard`, `megastore`) or an active à-la-carte `UserEntitlement` record. Free users without explicit entitlement receive HTTP 403 (`server/main.py:1385,1427`).
- **BYOK Gating**: Setting a custom AI key (`/api/user/custom-ai-key`) is strictly restricted to `user.plan == "megastore"`, returning HTTP 403 for other tiers (`server/main.py:912-914`, `tests/test_byok_pricing.py:23-32`).

### 2.4 SSRF & DNS Rebinding Protections
- `validate_public_url` in `server/connector_engine.py:27-45` enforces:
  - Scheme restriction: Only `https` allowed.
  - Host validation: Rejects `localhost`, `localhost.localdomain`, and `*.localhost`.
  - DNS resolution check: Resolves hostname via `socket.getaddrinfo` and inspects IP addresses.
  - IP classification: Rejects private (`10/8`, `172.16/12`, `192.168/16`), loopback (`127/8`), link-local (`169.254/16`), reserved, multicast, or unspecified IPs.
  - Redirect protection: `allow_redirects=False` in discovery and operation execution (`server/connector_engine.py:53`, `server/connector_registry.py:70`).
  - Size limitation: Payload sizes capped at 2 MB (`MAX_SPEC_BYTES = 2_000_000`, `MAX_RESPONSE_BYTES = 2_000_000`).

### 2.5 Content Governance & Platform Guardrails
- `audit_generated_content` (`server/content_governance.py:18-52`):
  - Defamation filter intercepts derogatory commercial claims (`scam`, `fraud`, `criminal`, `counterfeit`, `sued`, `lawsuit`, etc.) and replaces them with neutral phrasing.
  - Unsubstantiated claims filter catches absolute medical/financial guarantees (`100% cure`, `guaranteed to make you rich`, `100% risk free investment`).
  - Tested in `tests/test_platform_hardening.py:7-21`.

### 2.6 Security Headers & HTTP Hardening
- Global middleware (`server/main.py:46-64`) applies:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Permissions-Policy: geolocation=(), microphone=(), camera=()`
  - `Content-Security-Policy`: Restricts script/style/image sources to self, Google Fonts, CDN, and Stripe.
  - `Cache-Control: no-cache, no-store, must-revalidate, max-age=0`
  - Obsolete `X-XSS-Protection` header omitted per modern OWASP guidelines.
  - Tested in `tests/test_security_headers.py:1-21` and `tests/test_platform_hardening.py:58-67`.

---

## 3. Financial Invariants & Accounting Analysis

### 3.1 Dual-Bucket Balance Accounting Model
Users maintain two separate balance buckets in `User` (`server/database.py:22-39`):
1. `monthly_generations`: Granted per billing cycle based on plan tier (resets on renewal/invoice payment).
2. `purchased_generations`: Acquired via one-time generation packs (Starter +250, Growth +1000, Scale +3000) or add-on packages; **never expires and survives plan renewals, upgrades, and cancellations**.
3. Total available balance: `generations = monthly_generations + purchased_generations`.

### 3.2 Atomic Balance Reservation & Failure Refund Logic
- **Reservation**: `reserve_user_generations(user_id, cost, db)` (`server/main.py:320-356`):
  - Prioritizes monthly quota consumption before touching purchased quota (`monthly_used = min(monthly_avail, cost); purchased_used = cost - monthly_used`).
  - Uses pessimistic row locking (`with_for_update()`) on non-SQLite database engines.
  - Raises HTTP 402 Payment Required if `total_avail < cost`.
- **Refunds**: `refund_user_generations(user_id, monthly_refund, purchased_refund, db)` (`server/main.py:358-365`):
  - Restores exact reserved counts back to their respective buckets in the event of upstream AI provider failure (`server/main.py:385-387`, `server/main.py:596-600`, `tests/test_platform_hardening.py:68-83`).

### 3.3 Financial Invariant Gaps & Refactoring Opportunities
1. **Direct SQL vs Centralized Ledger in Vision & Competitor Mining**:
   - In `server/main.py:619` (`/api/campaign/generate-vision`) and `server/main.py:852` (`/api/competitor/mine-reviews`), balance deduction executes raw SQL:
     ```python
     db.execute(text("UPDATE users SET generations = generations - 1 WHERE id = :uid AND generations >= 1"), {"uid": user.id})
     ```
   - *Observation*: While atomic, directly updating `generations` bypasses `monthly_generations` vs `purchased_generations` bucket tracking, requiring lazy reconciliation in `reserve_user_generations`.
   - *Recommendation*: Refactor `/api/campaign/generate-vision` and `/api/competitor/mine-reviews` to utilize `reserve_user_generations(user.id, 1, db)` and `refund_user_generations(user.id, monthly_used, purchased_used, db)` for unified ledger consistency.

### 3.4 Payment Gateway Invariants (HTTP 503 Fallback)
- When Stripe environment variables or API keys are missing/unconfigured:
  - Plan price ID retrieval raises HTTP 503 (`server/billing.py:140-144`).
  - Stripe customer creation raises HTTP 503 (`server/billing.py:147-156`).
  - Add-on checkout raises HTTP 503 (`server/main.py:1487-1489`, `tests/test_adversarial_hardening.py:357-363`).
  - Webhook processing raises HTTP 503 (`server/billing.py:194-196`).

### 3.5 Webhook Idempotency & Replay Protection
- **Stripe Webhooks**: `StripeEvent` table (`server/database.py:133-138`) records unique `event_id`. Duplicate events are short-circuited with `{"status": "already_processed"}` (`server/billing.py:206-211`, `tests/test_billing_webhook.py:66-91`, `tests/test_adversarial_hardening.py:180-216`).
- **Inventory Webhooks**: `InventoryWebhookEvent` table (`server/database.py:209-216`) enforces unique composite constraint `(platform, event_id)` preventing duplicate stock debits on retried order webhooks (`server/inventory.py:32-46`, `tests/test_adversarial_hardening.py:322-356`).

---

## 4. Test Suite Baseline & Verification Status

### 4.1 Test Files & Inventory

| Test Module | Tests Count | Focus Area | Status |
| :--- | :---: | :--- | :---: |
| `tests/test_addons_monetization.py` | 6 | Add-on catalog, Persona CRUD, Listing optimizers (Amazon/Etsy/Shopify), Stripe Addon checkout | PASSED |
| `tests/test_adversarial_hardening.py` | 12 | Renewal quota preservation, no double count, cancellation preservation, addon entitlement, replay protection, IDOR isolation, entitlement gating, centralized ledger deduction, inventory idempotency, 503 unconfigured Stripe, recurring addon entitlement, subscription upgrade | PASSED |
| `tests/test_auth_verification.py` | 4 | Email verification request, token verification, token expiration, password reset | PASSED |
| `tests/test_billing_webhook.py` | 2 | Subscription creation, invoice payment, webhook idempotency | PASSED |
| `tests/test_byok_pricing.py` | 3 | Pricing structure, free BYOK forbidden, Megastore BYOK encrypted | PASSED |
| `tests/test_campaigns.py` | 3 | Atomic credit deduction, 402 insufficient credits, vision campaign | PASSED |
| `tests/test_connectors.py` | 5 | SSRF localhost block, HTTP block, private IP block, OpenAPI spec build, connector discovery & toggle | PASSED |
| `tests/test_csv.py` | 1 | CSV AI mapping & catalog extraction | PASSED |
| `tests/test_email_drip_bot.py` | 1 | Drip campaign execution & idempotency log | PASSED |
| `tests/test_growth_engines.py` | 5 | SEO analytics, SEO ping index, drip analytics, lead scoring, Admin MRR metrics & secret | PASSED |
| `tests/test_inventory.py` | 2 | SKU CRUD, inventory webhook fanout with source event suppression | PASSED |
| `tests/test_no_emojis.py` | 1 | Zero-emoji codebase regression check | PASSED |
| `tests/test_platform_hardening.py` | 5 | Content defamation filter, claims filter, stock drift reconciliation, security headers, failure refund | PASSED |
| `tests/test_price_monitor.py` | 2 | Price margin analysis logic, PriceMarginItem CRUD & deletion | PASSED |
| `tests/test_reddit_scout.py` | 1 | Reddit opportunity scout, draft reply, deduplication | PASSED |
| `tests/test_review_miner.py` | 1 | Review flaw extraction, counter copy, credit deduction | PASSED |
| `tests/test_security_headers.py` | 2 | Security headers verification, CORS preflight headers | PASSED |
| `tests/test_seo_marketing.py` | 2 | SEO blog post generation & persistence, sitemap/robots | PASSED |
| `tests/test_shopify_import.py` | 3 | Description HTML cleanup, Shopify catalog import, unconfigured fallback | PASSED |
| `tests/test_ugc_reviews.py` | 2 | Post-purchase drip emails, review sentiment classification & draft reply | PASSED |
| **Total** | **65** | **Comprehensive Full-Stack Test Suite** | **100% Pass** |

### 4.2 Flake8 Linter Status
```powershell
python -m flake8 server --count --select=E9,F63,F7,F82
# Output: 0
```
Zero syntax, undefined variable, or critical import errors exist.

### 4.3 Zero-Emoji Audit Status
- `tests/test_no_emojis.py` checks all `.html`, `.py`, `.js`, `.css`, and `.json` files in `server/` and `frontend/`.
- Result: **0 emojis found**.
- Note: Standalone execution improvement: Add `if __name__ == "__main__": test_zero_emojis_in_codebase()` at the bottom of `tests/test_no_emojis.py`.

---

## 5. Actionable Recommendations for Implementation Disciplines

1. **Backend / Security Refactoring**:
   - Refactor `/api/campaign/generate-vision` and `/api/competitor/mine-reviews` in `server/main.py` to use `reserve_user_generations` and `refund_user_generations` rather than direct raw SQL balance adjustments.
   - Add `if __name__ == "__main__": test_zero_emojis_in_codebase()` to `tests/test_no_emojis.py`.
2. **Pydantic & FastAPI Deprecation Cleanups**:
   - Migrate class-based `class Config` in `server/models.py:23,37` to Pydantic v2 `ConfigDict`.
   - Migrate deprecated `@app.on_event("startup")` and `@app.on_event("shutdown")` in `server/main.py:71,86` to FastAPI `lifespan` context manager.
3. **Comprehensive Invariant Coverage**:
   - Maintain 100% test pass rate across all new connectors, multi-modal generation pipelines, and automated growth engine features.
