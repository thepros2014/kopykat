# Milestone 4 Investigation Report: Security Governance, Pydantic v2 Modernization & Test Architecture

**Author**: Explorer 3 (Milestone 4: Security Governance, Pydantic v2 & Test Architecture)  
**Date**: 2026-08-23T13:36:00Z  
**Working Directory**: `c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m4\explorer_3\`  

---

## 1. Observation

### 1.1 Multi-Tenant Data Scoping (`user_id == user.id`)
In `server/main.py` and `server/database.py`, user-scoped tables and their corresponding route queries were audited:

1. **API Keys** (`server/main.py:315, 317-318`):
   ```python
   # Line 315
   db.query(APIKey).filter(APIKey.user_id == current_user.id, APIKey.is_active == True).all()
   # Line 318
   if not revoke_api_key(key_id, current_user, db): raise HTTPException(status_code=404, detail="Key not found")
   ```
2. **Integrations & Push Jobs** (`server/main.py:485, 491, 501, 508, 656, 660`):
   ```python
   # Line 485:
   existing = db.query(UserIntegration).filter(UserIntegration.user_id == user.id, UserIntegration.platform == body.platform).first()
   # Line 508:
   job = db.query(PushJob).filter(PushJob.id == job_id, PushJob.user_id == user.id).first()
   # Line 656:
   camp = db.query(Campaign).filter(Campaign.id == body.campaign_id, Campaign.user_id == user.id).first()
   ```
3. **Custom Connectors & Audit Logs** (`server/main.py:676, 692, 715, 749, 782, 811`):
   ```python
   # Line 676:
   connectors = db.query(CustomConnector).filter(CustomConnector.user_id == user.id).order_by(CustomConnector.created_at.desc()).all()
   # Line 692:
   c = db.query(CustomConnector).filter(CustomConnector.id == connector_id, CustomConnector.user_id == user.id).first()
   ```
4. **Inventory Balancer** (`server/main.py:932, 956, 1031`):
   ```python
   # Line 932:
   items = db.query(InventoryItem).filter(InventoryItem.user_id == user.id).order_by(InventoryItem.updated_at.desc()).all()
   # Line 956:
   item = db.query(InventoryItem).filter(InventoryItem.user_id == user.id, InventoryItem.sku == clean_sku).first()
   # Line 1031:
   logs = db.query(InventorySyncLog).filter(InventorySyncLog.user_id == user.id).order_by(InventorySyncLog.created_at.desc()).limit(50).all()
   ```
5. **Customer Reviews & UGC** (`server/main.py:1087, 1119`):
   ```python
   # Line 1119:
   reviews = db.query(CustomerReview).filter(CustomerReview.user_id == user.id).order_by(CustomerReview.created_at.desc()).limit(100).all()
   ```
6. **Price & Margin Monitor** (`server/main.py:1140, 1163, 1201`):
   ```python
   # Line 1140:
   items = db.query(PriceMarginItem).filter(PriceMarginItem.user_id == user.id).order_by(PriceMarginItem.updated_at.desc()).all()
   # Line 1201:
   item = db.query(PriceMarginItem).filter(PriceMarginItem.id == item_id, PriceMarginItem.user_id == user.id).first()
   ```
7. **Brand Voice Persona & Listing Optimizer** (`server/main.py:1363, 1383, 1425`):
   ```python
   # Line 1363:
   persona = db.query(BrandPersona).filter(BrandPersona.user_id == user.id).first()
   # Line 1425:
   persona_row = db.query(BrandPersona).filter(BrandPersona.user_id == user.id).first()
   ```
8. **Shopify Direct Import** (`server/main.py:1230`):
   ```python
   # Line 1230:
   integ = db.query(UserIntegration).filter(UserIntegration.user_id == user.id, UserIntegration.platform == "shopify", UserIntegration.status == "connected").first()
   ```
9. **Usage & Subscription Status** (`server/main.py:412, 415`):
   ```python
   # Line 412:
   sub = db.query(Subscription).filter(Subscription.user_id == current_user.id, Subscription.status == "active").first()
   # Line 415:
   agg = db.query(func.count(UsageRecord.id).label("total_requests"), func.sum(UsageRecord.generations_used).label("total_generations")).filter(UsageRecord.user_id == current_user.id).first()
   ```

*Shared / Public Entities*:
- `BlogPost` (`server/main.py:1288`): Public marketing blog articles (`BlogPost.published == True`).
- `OpportunityLog` (`server/main.py:1270`): Scraped global Reddit opportunity leads, accessible to authenticated users.

---

### 1.2 Fernet Credential Encryption
In `server/auth.py:208-226`:
```python
_INTEGRATION_KEY = os.getenv("INTEGRATION_ENCRYPTION_KEY")
if not _INTEGRATION_KEY:
    _INTEGRATION_KEY = "kopykatEnterpriseEncryptionKey2026AAA="

try:
    _fernet = Fernet(_INTEGRATION_KEY.encode())
except Exception:
    import base64
    _fallback_32 = base64.urlsafe_b64encode(b"kopykat-enterprise-secret-key-32")
    _fernet = Fernet(_fallback_32)

def encrypt_credentials(data: str) -> str:
    return _fernet.encrypt(data.encode()).decode()

def decrypt_credentials(data: str) -> str:
    return _fernet.decrypt(data.encode()).decode()
```
- Used for encrypting `UserIntegration.credentials` (`server/main.py:485, 719`).
- Used for decrypting integration credentials on push/sync (`server/main.py:495, 503, 662, 761, 1237`, `server/integrations.py:85`).
- Used for encrypting BYOK custom AI API keys in `User.custom_ai_key_encrypted` (`server/main.py:911`).

---

### 1.3 Bcrypt Password Hashing & 72 UTF-8 Bytes Enforcement
In `server/auth.py:37-58`:
```python
def hash_password(password: str) -> str:
    """Hash password using bcrypt directly."""
    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > 72:
        raise HTTPException(status_code=400, detail="Password is too long; maximum is 72 UTF-8 bytes")
    return bcrypt.hashpw(pwd_bytes, bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    """Verify password against bcrypt hash."""
    try:
        pwd_bytes = plain.encode("utf-8")
        if len(pwd_bytes) > 72:
            return False
        return bcrypt.checkpw(pwd_bytes, hashed.encode("utf-8"))
    except Exception:
        return False
```
In `server/models.py:10, 107`:
- `UserRegister`: `password: str = Field(min_length=8, max_length=72)`
- `ResetPasswordSubmit`: `new_password: str = Field(min_length=8, max_length=72)`

---

### 1.4 Pydantic v2 Modernization in `server/models.py`
In `server/models.py`, two models contain legacy Pydantic v1 `class Config`:
1. `UserProfile` (lines 31-32):
   ```python
   class UserProfile(BaseModel):
       id: str
       email: str
       full_name: Optional[str]
       plan: str
       generations: int
       monthly_limit: int
       created_at: datetime
       class Config:
           from_attributes = True
   ```
2. `APIKeyResponse` (lines 45-46):
   ```python
   class APIKeyResponse(BaseModel):
       id: str
       key_prefix: str
       name: str
       is_active: bool
       last_used: Optional[datetime]
       requests_today: int
       created_at: datetime
       class Config:
           from_attributes = True
   ```
**Direct Warning Output Observed from Pytest**:
```
server\models.py:23: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0. See Pydantic V2 Migration Guide at https://errors.pydantic.dev/2.13/migration/
server\models.py:37: PydanticDeprecatedSince20: Support for class-based `config` is deprecated, use ConfigDict instead.
```

---

### 1.5 Frontend Dashboard & Admin Markup Audit
1. `frontend/admin.html`:
   - Admin UI currently queries `/api/admin/stats`.
   - Requires integration with `/admin/mrr-metrics` to render MRR, ARR, subscriber tier breakdown, valuation estimates, and telemetry stats.
2. `frontend/dashboard.html`:
   - Sidebar contains navigation links for 9 tools (lines 65-73).
   - JavaScript implementation contains functions: `runReviewMiner`, `loadInventory`, `saveInventoryItem`, `quickAdjustStock`, `generateUGCDrip`, `loadCustomerReviews`, `loadPriceItems`, `savePriceItem`, `deletePriceItem`, `loadOpportunityLeads`, `loadGrowthAnalytics`, `pingSearchEngines`, `loadBrandPersona`, `saveBrandPersona`, `optimizeMarketplaceListing`, `loadAddOnsStore`, `buyAddon`, `loadCustomAIKeyStatus`, `saveCustomAIKey`.
   - **Missing Markup**: The HTML body (`<main class="main-content">`) lacks the 9 corresponding `<section id="section-...">` markup blocks:
     - `section-miner`
     - `section-inventory`
     - `section-ugc`
     - `section-pricing-monitor`
     - `section-leads`
     - `section-growth`
     - `section-brand-persona`
     - `section-listing-optimizer`
     - `section-addons-store`

---

## 2. Logic Chain

1. **Multi-Tenant Isolation**:
   - Because all database queries for tenant data filter by `user_id == current_user.id` or `User.id == current_user.id`, User A is strictly isolated from User B.
   - When User A requests a specific resource ID (e.g. `connector_id`, `item_id`, `job_id`, `key_id`) that belongs to User B, the query returns `None`, raising HTTP 404.

2. **Fernet Encryption**:
   - Marketplace credentials and custom AI API keys contain sensitive secret credentials (OAuth refresh tokens, secret keys, API tokens).
   - By storing these solely as Fernet ciphertexts generated with `encrypt_credentials(data)` and decrypting them on demand in memory with `decrypt_credentials(ciphertext)`, credentials are encrypted at rest in SQLite/PostgreSQL.

3. **Bcrypt 72-Byte Boundary**:
   - Bcrypt natively truncates passwords at 72 bytes. If a backend blindly passes a longer password to bcrypt, passwords with identical first 72 bytes collide.
   - By validating `len(password.encode("utf-8")) <= 72` in `hash_password`, passwords exceeding 72 UTF-8 bytes are rejected with HTTP 400. `verify_password` returns `False` for passwords > 72 bytes.

4. **Pydantic v2 Modernization**:
   - `class Config:` was the Pydantic v1 configuration approach.
   - In Pydantic v2, `model_config = ConfigDict(from_attributes=True)` is the standard mechanism to allow ORM model deserialization.
   - Replacing `class Config:` eliminates deprecation warnings and prevents future breaking changes.

5. **Test Suite Architecture (`tests/test_frontend_admin_m4.py`)**:
   - To provide comprehensive regression testing for Milestone 4, `tests/test_frontend_admin_m4.py` should be created with the 7 critical test suites detailed below.

---

## 3. Caveats

1. `tests/test_frontend_admin_m4.py` is a new test suite to be authored in M4 by the test engineer/implementer.
2. In `frontend/admin.html`, JavaScript fetching functions can be extended to fetch both `/api/admin/stats` and `/admin/mrr-metrics`.
3. In `frontend/dashboard.html`, all 9 `<section>` blocks need to be inserted into `<main>` with matching element IDs referenced in the existing JS.

---

## 4. Conclusion & Actionable Specifications

### 4.1 Pydantic v2 Modernization Proposal for `server/models.py`
Replace:
```python
from pydantic import BaseModel, EmailStr, Field
```
with:
```python
from pydantic import BaseModel, ConfigDict, EmailStr, Field
```
And replace lines 31-32 & lines 45-46:
```python
class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    full_name: Optional[str]
    plan: str
    generations: int
    monthly_limit: int
    created_at: datetime

class APIKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    key_prefix: str
    name: str
    is_active: bool
    last_used: Optional[datetime]
    requests_today: int
    created_at: datetime
```

---

### 4.2 Comprehensive Specifications for `tests/test_frontend_admin_m4.py`

The new test file `tests/test_frontend_admin_m4.py` should contain:

```python
"""
tests/test_frontend_admin_m4.py
Milestone 4 Test Suite:
1. Admin MRR metrics endpoint and frontend rendering verification.
2. All 9 dashboard sections rendering and structural presence.
3. Dual-bucket quota reservation and refund mechanisms.
4. Stripe 503 on unconfigured gateway.
5. BYOK Megastore gating.
6. Multi-tenant scoping and Fernet encryption.
7. Flake8 linting and zero-emoji compliance.
"""
```

#### Detailed Test Cases to Include:
1. **Suite 1: Admin MRR & Telemetry UI**
   - `test_m4_admin_page_renders_html(client)`: Verify GET `/admin` returns HTTP 200 with complete admin layout.
   - `test_m4_admin_mrr_metrics_forbidden_without_secret(client)`: Verify GET `/admin/mrr-metrics` returns 403 without `X-Admin-Secret`.
   - `test_m4_admin_mrr_metrics_calculation(client, db_session)`: Seed active subscriptions for Boutique ($179.49), Standard ($379.49), and Megastore ($9,639.63). Verify `mrr_usd`, `arr_usd == round(mrr * 12, 2)`, `tier_counts`, `software_asset_score == 9.2`, and `valuation_estimate_usd`.

2. **Suite 2: Dashboard 9 Sections Structural Presence**
   - `test_m4_dashboard_all_nine_sections_present(client)`: Read `frontend/dashboard.html` and verify the DOM presence of all 9 `<section>` tags:
     - `section-miner` (with `#miner-product`, `#miner-reviews`, `#btn-mine-reviews`, `#miner-results-area`)
     - `section-inventory` (with `#inv-sku`, `#inv-title`, `#inv-qty`, `#inv-table-body`, `#inv-logs-list`)
     - `section-ugc` (with `#ugc-prod`, `#ugc-tone`, `#ugc-incentive`, `#btn-gen-ugc-drip`, `#ugc-reviews-list`)
     - `section-pricing-monitor` (with `#pm-sku`, `#pm-title`, `#pm-cogs`, `#pm-retail`, `#pm-table-body`)
     - `section-leads` (with `#leads-feed-list`)
     - `section-growth` (with `#stat-seo-posts`, `#stat-seo-words`, `#stat-drips-sent`, `#stat-paid-subscribers`)
     - `section-brand-persona` (with `#persona-brand-name`, `#persona-voice-tone`, `#persona-audience`, `#persona-guidelines`)
     - `section-listing-optimizer` (with `#opt-platform`, `#opt-product-name`, `#opt-raw-details`, `#optimizer-results-card`)
     - `section-addons-store` (with `#addons-grid`)

3. **Suite 3: Dual-Bucket Quota Reservation & Atomic Refund**
   - `test_m4_reserve_generations_monthly_then_purchased(db_session, test_user)`: User with 10 monthly and 20 purchased reserving 15 consumes 10 monthly and 5 purchased; remaining balance is 0 monthly, 15 purchased (15 total).
   - `test_m4_reserve_generations_insufficient_raises_402(db_session, test_user)`: User with 2 monthly and 3 purchased requesting 10 raises HTTP 402.
   - `test_m4_refund_generations_restores_buckets(db_session, test_user)`: `refund_user_generations(user.id, monthly_refund=5, purchased_refund=5, db=db_session)` restores exact bucket values.
   - `test_m4_ai_generation_failure_triggers_atomic_refund(client, auth_headers, test_user, db_session)`: Upstream error during `/api/generate` or `/api/campaign/generate` restores deducted credits and returns 500 error.

4. **Suite 4: Payment Gateway Fault Tolerance (Stripe 503)**
   - `test_m4_stripe_unconfigured_returns_503(client, auth_headers, monkeypatch)`: Setting `stripe.api_key = ""` on POST `/billing/addon/checkout` returns HTTP 503 `"Stripe is not configured. Payment gateway unavailable."`.

5. **Suite 5: BYOK Megastore Gating**
   - `test_m4_byok_gating_forbidden_for_free_and_boutique_and_standard(client, auth_headers, test_user, db_session)`: Verify non-Megastore plans receive 403.
   - `test_m4_byok_allowed_for_megastore_with_fernet(client, auth_headers, test_user, db_session)`: Megastore user sets key; verify key is encrypted in DB, status returns `unlimited_active: true`, and DELETE clears key.

6. **Suite 6: Multi-Tenant Scoping & Fernet IDOR Protection**
   - `test_m4_multitenant_inventory_and_persona_and_connectors_isolation(client, db_session)`: User A cannot read or delete User B's inventory items, brand persona, connectors, or price margin items.
   - `test_m4_fernet_encryption_roundtrip()`: Validates `encrypt_credentials` and `decrypt_credentials` roundtrip.

7. **Suite 7: Zero-Emoji and Flake8 Compliance**
   - `test_m4_zero_emojis_in_frontend_and_server()`: Regex scan confirms 0 emojis across `server/` and `frontend/`.
   - `test_m4_flake8_clean_codebase()`: Runs flake8 check with 0 syntax/undefined variable errors.

---

## 5. Verification Method

To independently verify these findings:

1. **Verify Pydantic v2 Warning Elimination**:
   ```pwsh
   python -m pytest tests/test_auth_verification.py -v -W error::pydantic.PydanticDeprecatedSince20
   ```
2. **Verify Zero Emojis in Codebase**:
   ```pwsh
   python -m pytest tests/test_no_emojis.py -v
   ```
3. **Verify Flake8 Cleanliness**:
   ```pwsh
   python -m flake8 server tests --count --select=E9,F63,F7,F82
   ```
4. **Inspect Dashboard Sections in `frontend/dashboard.html`**:
   Search for `<section id="section-` in `frontend/dashboard.html`.
5. **Run the Complete Test Suite**:
   ```pwsh
   python -m pytest tests/ -v
   ```
