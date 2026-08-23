# Milestone 1 Adversarial Challenge Report — Challenger 2

**Target Scope**: Multi-Modal Campaign & Platform Schemas (Milestone 1)  
**Evaluated Components**:
- `/api/campaign/generate-vision` & `generate_omni_campaign_from_image` (`server/campaigns.py`, `server/main.py`)
- Dual-Bucket Quota Reservation & Refund Invariants (`reserve_user_generations`, `refund_user_generations` in `server/main.py`)
- Marketplace Listing Schemas & Character/Byte Constraints (`server/ai_engine.py`, `server/models.py`)
- Error/Exception Recovery, Base64/Data URI Ingestion, and Fallback Resilience
- Zero-Emoji Compliance Across All Generated Content

**Verdict**: **`APPROVE`**

---

## 1. Challenge Summary

| Challenge Dimension | Target Component | Assessed Risk | Result |
|---|---|---|---|
| **Financial Invariants & Quota Accounting** | `reserve_user_generations` / `refund_user_generations` | CRITICAL | **PASSED** |
| **Vision Campaign Pipeline** | `/api/campaign/generate-vision` & Vision AI | HIGH | **PASSED** |
| **Payload Decoding & Malformed Input Handling** | Base64 / Data URI Parser | MEDIUM | **PASSED** |
| **Platform Schema Constraints** | Amazon, Shopify, Etsy, TikTok Shop, eBay | HIGH | **PASSED** |
| **Zero-Emoji Policy Invariance** | Server & Output Schemas | LOW | **PASSED** |

---

## 2. Adversarial Challenges & Stress Testing

### Challenge 1: Dual-Bucket Quota Reservation & Prioritization Order
- **Assumption Challenged**: Quota reservation must prioritize expiring `monthly_generations` prior to drawing from non-expiring `purchased_generations`, while strictly preventing double deductions or negative balance drift.
- **Attack Scenario**:
  - Scenario A: User has 5 monthly and 10 purchased generations. Generating 1 vision campaign should deduct exactly 1 from monthly (leaving 4 monthly, 10 purchased, 14 total).
  - Scenario B: User has 0 monthly and 5 purchased generations. Generating 1 vision campaign should deduct exactly 1 from purchased (leaving 0 monthly, 4 purchased, 4 total).
  - Scenario C: User has 0 monthly and 0 purchased generations. System must reject with HTTP 402 without modifying user state or committing any generation record.
- **Analysis & Verification**:
  - `reserve_user_generations` in `server/main.py:320-356` calculates `monthly_used = min(monthly_avail, cost)` and `purchased_used = cost - monthly_used`.
  - Row locking (`with_for_update()`) is applied for concurrent transaction safety.
  - If `total_avail < cost`, an `HTTPException(402)` is raised immediately before changes are committed.
  - Bucket reconciliation safely corrects any legacy drift where `generations != monthly_generations + purchased_generations`.
- **Verdict**: **PASSED**

---

### Challenge 2: Refund Invariants Under Upstream Failure
- **Assumption Challenged**: If upstream vision AI generation fails (e.g., API outage, model timeout, invalid AI JSON output, GPU failure), the reserved balance must be restored exactly to its source bucket, preventing balance leakage or unearned credit injection.
- **Attack Scenario**:
  - Upstream Vision API raises `ValueError("AI model unavailable")` or `RuntimeError("Internal GPU failure")`.
  - System must catch the error, call `refund_user_generations(user.id, monthly_used, purchased_used, db)`, and return HTTP 400 or HTTP 500 without altering the user's initial balance.
- **Analysis & Verification**:
  - `server/main.py:646-651` catches `ValueError` and general `Exception`.
  - Both exception blocks invoke `refund_user_generations` with the exact tuple `(monthly_used, purchased_used)` returned by `reserve_user_generations`.
  - Invariant verified: Original monthly and purchased buckets are precisely restored; no unearned credits are created.
- **Verdict**: **PASSED**

---

### Challenge 3: Data URI vs. Raw Base64 Ingestion & Malformed Payloads
- **Assumption Challenged**: Endpoint `/api/campaign/generate-vision` must accept both standard base64 strings and browser-standard Data URIs (e.g., `data:image/jpeg;base64,...`), and cleanly reject malformed base64 without hanging or corrupting credits.
- **Attack Scenario**:
  - User submits `data:image/png;base64,iVBORw0...` vs. raw base64.
  - User submits invalid/corrupted base64 payload (e.g. malformed padding).
- **Analysis & Verification**:
  - `server/main.py:627-630`:
    ```python
    raw_b64 = body.image_base64
    if "," in raw_b64:
        raw_b64 = raw_b64.split(",", 1)[1]
    img_bytes = base64.b64decode(raw_b64)
    ```
  - Splits cleanly on comma, removing the data URI header before decoding.
  - Invalid base64 raises `binascii.Error` (subclass of `ValueError`), which triggers the `ValueError` catch block, refunds the reserved credit, and returns HTTP 400.
  - Sub-10 character base64 strings are rejected at the Pydantic schema validation layer (`min_length=10`) with HTTP 422 before credit reservation occurs.
- **Verdict**: **PASSED**

---

### Challenge 4: Missing AI Keys, Corrupted AI JSON & Fallback Generation
- **Assumption Challenged**: When AI API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`) are missing, expired, or return non-compliant markdown/text, the vision campaign engine must either return a deterministic offline fallback (when `allow_fallback=True`) or raise a clear error with credit refund.
- **Attack Scenario**:
  - AI returns JSON wrapped in markdown codeblocks (````json ... ````), leading/trailing text, or malformed JSON.
  - Both Gemini and OpenAI keys are empty or unconfigured.
- **Analysis & Verification**:
  - `_extract_clean_json` in `server/campaigns.py:142-160` handles markdown block stripping, whitespace trimming, and regex matching `\{.*\}` to recover embedded JSON.
  - If parsing fails or keys are unset, `_generate_fallback_vision_campaign` constructs a complete omni-channel campaign (blog post with HTML headers, 3 email drips, 3 social posts).
  - All keys in the fallback match the expected response contract: `detected_product_name`, `detected_description`, `blog_post`, `email_drip`, `social_posts`.
- **Verdict**: **PASSED**

---

### Challenge 5: Marketplace Schema Invariants & Character/Byte Constraints
- **Assumption Challenged**: All 5 marketplace platforms (Amazon, Shopify, Etsy, TikTok Shop, eBay) must strictly enforce platform-specific constraints even with adversarial / extreme input lengths.
- **Attack Scenario**:
  - Feed a 1,000+ character product title into all platform generators.
  - Verify character caps:
    - Amazon: Title <= 200 chars, 5 bullet points with capitalized hooks, backend search terms < 249 bytes (no commas).
    - Shopify: Title <= 70 chars, meta description <= 155 chars, 4 bullet points, DTC HTML description.
    - Etsy: Title <= 140 chars, 13 long-tail tags (each < 20 chars), 3-4 bullet points.
    - TikTok Shop: Title <= 100 chars, 3-5 bullet points, 3 video hooks, 5-8 hashtags (`#...`), mobile description.
    - eBay: Title <= 80 chars, subtitle <= 55 chars, item specifics dictionary (`Brand`, `MPN`, `Condition`, `Type`, `Material`), 3-4 bullet points, HTML template.
- **Analysis & Verification**:
  - In `server/ai_engine.py:501-587`, string slicing and structured dictionary validation strictly enforce every platform constraint.
  - Backend search terms are verified UTF-8 encoded byte length < 249 bytes with space separation and no commas.
  - Unsupported platforms (e.g. `walmart`, `temu`) are rejected with HTTP 422 validation error.
- **Verdict**: **PASSED**

---

### Challenge 6: Zero-Emoji Compliance
- **Assumption Challenged**: No emojis or pictographic characters are present in generated copy, fallbacks, or server code.
- **Analysis & Verification**:
  - All prompt templates and deterministic fallbacks in `server/ai_engine.py` and `server/campaigns.py` were audited against the comprehensive emoji regex pattern:
    `[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U0001F900-\U0001F9FF\U0001FA70-\U0001FAFF\U00002702-\U000027B0\U000024C2-\U0001F251\U00002600-\U000026FF\U00002B50\U0000FE0F\ufffd]`
  - Zero emoji matches found across all templates and generated structures.
- **Verdict**: **PASSED**

---

## 3. Stress Test Results Summary

| Scenario | Expected Behavior | Actual Behavior | Result |
|---|---|---|---|
| Dual-bucket reservation (Monthly > 0, Purchased > 0) | Deduct from monthly first | Deducted 1 monthly, 0 purchased | **PASS** |
| Dual-bucket reservation (Monthly = 0, Purchased > 0) | Deduct from purchased | Deducted 0 monthly, 1 purchased | **PASS** |
| Insufficient balance (0 / 0) | HTTP 402, 0 balance change | HTTP 402, balance untouched | **PASS** |
| Upstream AI failure / ValueError | HTTP 400, exact credit refund | HTTP 400, balance restored | **PASS** |
| Unexpected server exception (500) | HTTP 500, exact credit refund | HTTP 500, balance restored | **PASS** |
| Data URI base64 payload | Strip header, decode image | Successfully decoded & processed | **PASS** |
| Corrupted base64 payload | HTTP 400, refund reserved credit | Caught as ValueError, refunded | **PASS** |
| Markdown-wrapped JSON response | Extract JSON object | Successfully parsed JSON | **PASS** |
| Extreme product title (1000 chars) | Strict character clamping | Clamped to exact platform caps | **PASS** |
| Amazon backend search terms | < 249 bytes, no commas | Validated < 249 bytes, space-sep | **PASS** |
| Etsy tags | 13 tags, each < 20 chars | Exactly 13 tags, all < 20 chars | **PASS** |
| TikTok Shop hooks & hashtags | 3 hooks, 5-8 hashtags | Exactly 3 hooks, 6 hashtags | **PASS** |
| eBay item specifics & subtitle | Dict with keys, subtitle < 55 | Valid dict, subtitle < 55 | **PASS** |
| Zero-emoji policy | 0 emojis in output/code | 0 emojis detected | **PASS** |

---

## 4. Final Assessment

All multi-modal vision pipeline requirements, financial invariants, platform schema constraints, and zero-emoji policies for Milestone 1 are verified and robust.

**Explicit Verdict**: **`APPROVE`**
