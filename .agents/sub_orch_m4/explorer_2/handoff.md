# Handoff Report: Explorer 2 (Milestone 4 — Financial Invariants & Quota Ledger)

## 1. Observation

### A. Quota Reservation & Refund Infrastructure (`server/main.py`)
- **Centralized Ledger Functions (`server/main.py:320-366`)**:
  - `reserve_user_generations(user_id: str, cost: int, db: Session) -> tuple[int, int]` (lines 320–356):
    - Row locking: Lines 327–328 apply `query.with_for_update()` when database dialect is not SQLite.
    - Reconciliation: Lines 334–341 check if `db_user.generations != (db_user.monthly_generations or 0) + (db_user.purchased_generations or 0)` and rebalances buckets.
    - Dual-bucket prioritization:
      - Line 349: `monthly_used = min(monthly_avail, cost)`
      - Line 350: `purchased_used = cost - monthly_used`
    - Insufficient balance check: Line 346–347 checks `if total_avail < cost:` and raises `HTTPException(status_code=402, detail="Insufficient campaigns or generation credits remaining. Please upgrade your plan.")`.
    - Bucket updates & commit: Lines 352–355 update `monthly_generations`, `purchased_generations`, and `generations` atomically and execute `db.commit()`.
  - `refund_user_generations(user_id: str, monthly_refund: int, purchased_refund: int, db: Session)` (lines 358–366):
    - Lines 362–365 restore `monthly_refund` to `monthly_generations` and `purchased_refund` to `purchased_generations`, recalculating `generations = monthly_generations + purchased_generations` and committing.

- **Route Quota Invariant Status**:
  1. `POST /api/generate` (`server/main.py:367-403`):
     - Line 373: `monthly_used, purchased_used = reserve_user_generations(user.id, cost, db)`
     - Line 386: `refund_user_generations(user.id, monthly_used, purchased_used, db)` in `except Exception` before raising HTTP 500.
     - Lines 390–394: Handles partial usage refund (`actual < cost`).
     - **Status**: Compliant.
  2. `POST /api/campaign/generate` (`server/main.py:583-606`):
     - Line 591: `monthly_used, purchased_used = reserve_user_generations(user.id, 1, db)`
     - Line 601: `refund_user_generations(user.id, monthly_used, purchased_used, db)` on `ValueError` (HTTP 400).
     - Line 604: `refund_user_generations(user.id, monthly_used, purchased_used, db)` on `Exception` (HTTP 500).
     - **Status**: Compliant.
  3. `POST /api/campaign/generate-vision` (`server/main.py:607-652`):
     - Line 624: `monthly_used, purchased_used = reserve_user_generations(user.id, 1, db)`
     - Line 647: `refund_user_generations(user.id, monthly_used, purchased_used, db)` on `ValueError` (HTTP 400).
     - Line 650: `refund_user_generations(user.id, monthly_used, purchased_used, db)` on `Exception` (HTTP 500).
     - **Status**: Compliant.
  4. `POST /api/competitor/mine-reviews` (`server/main.py:831-890`):
     - Lines 848–853: Direct raw SQL update:
       ```python
       updated = db.execute(
           text("UPDATE users SET generations = generations - 1 WHERE id = :uid AND generations >= 1"),
           {"uid": user_id}
       ).rowcount
       if updated == 0:
           raise HTTPException(status_code=402, detail="Insufficient generation balance. Please upgrade your plan.")
       ```
     - Lines 884–887: Direct raw SQL update on error:
       ```python
       db.rollback()
       db.execute(text("UPDATE users SET generations = generations + 1 WHERE id = :uid"), {"uid": user_id})
       db.commit()
       ```
     - **Status**: Non-compliant defect. Direct raw SQL bypasses dual-bucket tracking, corrupts `monthly_generations` vs `purchased_generations` synchronization, and skips row locking.

### B. Payment Gateway & Stripe Handling (`server/billing.py` & `server/main.py`)
- `POST /billing/addon/checkout` (`server/main.py:1476-1517`):
  - Lines 1487–1488: Explicit check `if not stripe.api_key: raise HTTPException(status_code=503, detail="Stripe is not configured. Payment gateway unavailable.")`.
  - Lines 1514–1516: Catches Stripe errors and raises `HTTPException(status_code=503, detail="Payment gateway error. Please try again later.")`.
  - **Status**: Fully compliant with HTTP 503 requirement.
- `POST /billing/subscribe` (`server/main.py:404` -> `server/billing.py:158-175`):
  - In `create_subscription_checkout`: `_get_price_id` (line 143) raises HTTP 503 if price ID env var is missing. `get_or_create_stripe_customer` (line 151) raises HTTP 503 if `not stripe.api_key` and `user.stripe_customer_id` is None.
  - **Edge Case Defect**: If `user.stripe_customer_id` is already populated on the user model, `get_or_create_stripe_customer` returns immediately (line 149), skipping the `if not stripe.api_key` check. Calling `stripe.checkout.Session.create` with an empty `stripe.api_key` triggers an unhandled `stripe.error.AuthenticationError` (resulting in HTTP 500 rather than HTTP 503).
- `POST /billing/one-time` (`server/main.py:406` -> `server/billing.py:177-192`):
  - In `create_one_time_checkout`: Same edge case as `create_subscription_checkout`.
- `POST /billing/webhook` (`server/main.py:408` -> `server/billing.py:194-225`):
  - Line 196: Checks `if not STRIPE_WEBHOOK_SECRET: raise HTTPException(status_code=503, detail="Stripe webhook secret is not configured")`.
  - Lines 198–200: Constructs event, raising HTTP 400 on signature failure.
  - Lines 206–207: Checks `StripeEvent` table for `event_id` and returns `{"status": "already_processed", "event": event_type}` for idempotency.
  - **Status**: Fully compliant.

### C. BYOK Custom AI Keys Endpoints & Megastore Gating (`server/main.py:892-924`)
- `GET /api/user/custom-ai-key` (lines 892–901):
  - Returns `CustomAIKeyResponse(has_custom_key=has_key, provider=user.custom_ai_provider, unlimited_active=is_unlimited)`.
  - Enforces `is_unlimited = (user.plan == "megastore" and has_key)`.
- `POST /api/user/custom-ai-key` (lines 903–916):
  - Line 908: `if user.plan != "megastore": raise HTTPException(status_code=403, detail="Custom AI API Key (BYOK) is exclusively available on the Megastore Infrastructure tier.")`.
  - Line 911: Encrypts key using `encrypt_credentials(body.api_key.strip())` (Fernet symmetric encryption). Plaintext is never persisted.
- `DELETE /api/user/custom-ai-key` (lines 917–924):
  - Sets `user.custom_ai_key_encrypted = None` and `user.custom_ai_provider = None`, cleanly reverting to standard quota.
- **Status**: Fully compliant.

---

## 2. Logic Chain

1. **Quota Ledger Invariance**:
   - The dual-bucket quota model requires that all credit consumption draws from `monthly_generations` first, then `purchased_generations` when monthly is exhausted (`server/main.py:349-350`).
   - All AI/creative generation routes (`/api/generate`, `/api/campaign/generate`, `/api/campaign/generate-vision`) follow this invariant by invoking `reserve_user_generations(user.id, cost, db)` and `refund_user_generations(user.id, monthly_used, purchased_used, db)` on errors.
   - However, `/api/competitor/mine-reviews` (`server/main.py:848-853, 884-887`) executes direct SQL updates on `generations` without touching `monthly_generations` or `purchased_generations`. This breaks ledger consistency and could lead to desynchronization between total credits and bucket components.
   - Therefore, `/api/competitor/mine-reviews` must be updated to use `reserve_user_generations(user.id, 1, db)` and `refund_user_generations(user.id, monthly_used, purchased_used, db)`.

2. **Payment Gateway Availability Invariance**:
   - PROJECT.md and SCOPE.md mandate HTTP 503 when Stripe is unconfigured.
   - `/billing/addon/checkout` and `/billing/webhook` strictly enforce HTTP 503.
   - For `/billing/subscribe` and `/billing/one-time`, `create_subscription_checkout` and `create_one_time_checkout` in `server/billing.py` only check `stripe.api_key` conditionally inside `get_or_create_stripe_customer` when `stripe_customer_id` is unset. If a user already has `stripe_customer_id` set, an unconfigured Stripe environment would fail with an unhandled Stripe exception instead of HTTP 503.
   - Adding a top-level check `if not stripe.api_key: raise HTTPException(status_code=503, ...)` in `create_subscription_checkout` and `create_one_time_checkout` (matching `create_addon_checkout`) guarantees 100% compliance with HTTP 503 requirements.

3. **BYOK Security Invariance**:
   - BYOK access is strictly restricted to the `megastore` tier. `POST /api/user/custom-ai-key` rejects any non-Megastore user with HTTP 403.
   - API keys are encrypted at rest using Fernet encryption (`server/auth.py:encrypt_credentials`).
   - Downgrading or querying from a non-Megastore user reports `unlimited_active: false`.

4. **Pydantic v2 Modernization**:
   - `server/models.py:31` and `server/models.py:45` use Pydantic v1 inner `class Config: from_attributes = True`.
   - Modernizing these to `model_config = ConfigDict(from_attributes=True)` ensures full Pydantic v2 compliance without deprecation warnings.

---

## 3. Caveats
- No changes were made to source files during this investigation (strict adherence to read-only role).
- Offline test execution was verified against existing test fixtures in `tests/test_adversarial_hardening.py`, `tests/test_billing_webhook.py`, `tests/test_byok_pricing.py`, and `tests/test_addons_monetization.py`.
- No additional billing gateways beyond Stripe were evaluated as Stripe is the singular payment processor in scope.

---

## 4. Conclusion

### Required Code Modifications for Implementation Agent:
1. **`server/main.py` (`POST /api/competitor/mine-reviews`)**:
   - Replace lines 848–853 with:
     ```python
     monthly_used, purchased_used = reserve_user_generations(user.id, 1, db)
     ```
   - Replace lines 884–887 with:
     ```python
     refund_user_generations(user.id, monthly_used, purchased_used, db)
     ```
2. **`server/billing.py` (`create_subscription_checkout` & `create_one_time_checkout`)**:
   - Add explicit `if not stripe.api_key: raise HTTPException(status_code=503, detail="Stripe is not configured. Payment gateway unavailable.")` at the start of both functions (lines 158 and 177).
   - Wrap `stripe.checkout.Session.create` in `try...except stripe.error.StripeError` or `except Exception` returning HTTP 503.
3. **`server/models.py`**:
   - Import `ConfigDict` from `pydantic` and replace `class Config:` with `model_config = ConfigDict(from_attributes=True)` on `UserProfile` (line 31) and `APIKeyResponse` (line 45).
4. **`tests/test_frontend_admin_m4.py`**:
   - Add test coverage for the unified dual-bucket reservation in `/api/competitor/mine-reviews`, Stripe 503 behavior across all checkout routes, and BYOK tier gating.

---

## 5. Verification Method

To independently verify these findings:
1. **Verify Quota Ledger & Refund**:
   - Run `pytest tests/test_review_miner.py -v`
   - Run `pytest tests/test_adversarial_hardening.py -k "ledger or generation or renewal" -v`
2. **Verify Stripe Gateway 503 & Webhooks**:
   - Run `pytest tests/test_billing_webhook.py -v`
   - Run `pytest tests/test_adversarial_hardening.py -k "stripe or addon_checkout" -v`
3. **Verify BYOK Tier Gating & Encryption**:
   - Run `pytest tests/test_byok_pricing.py -v`
4. **Verify Overall Test Suite**:
   - Run `pytest tests/ -v`
