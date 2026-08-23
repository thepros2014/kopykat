# Technical Investigation Report: Milestone 3 Growth Engine & Review Telemetry

**Agent**: Explorer 2 (Milestone 3 Sub-Orchestrator)  
**Date**: 2026-08-23  
**Working Directory**: `c:\Users\plumb\Desktop\claude-project\.agents\sub_orch_m3\explorer_2`  
**Scope Focus**:
1. Review Sentiment & UGC Drips (`server/reviews_ugc.py`)
2. 1-Star Competitor Flaw Miner (`server/ai_engine.py` / `server/reviews_ugc.py`)
3. Dynamic Competitor Price Monitoring & Alert Thresholds (`server/pricing_monitor.py`)

---

## 1. Executive Summary

A comprehensive, read-only architectural investigation was conducted across the KopyKat growth engine and review intelligence subsystems. The implementation was audited for functional correctness, schema validation, multi-tenant isolation, atomic financial/credit guarantees, flake8 lint compliance, zero-emoji policy adherence, and test coverage.

### Key Assessment Findings
- **Review Sentiment & UGC Drips (`server/reviews_ugc.py`)**: Fully implemented with 3-step post-purchase drip templates across days 3, 7, and 14, lexical sentiment classification into positive/neutral/negative, and automated merchant draft resolution replies.
- **1-Star Competitor Flaw Miner (`server/ai_engine.py`)**: Implemented via `mine_competitor_reviews()`, featuring structured LLM extraction of flaws, counter-positioned product descriptions, Us-vs-Them comparison points, direct-response ad hooks, content governance auditing (defamation/unsubstantiated claims filter), and atomic quota reservation with rollback refunds on failure.
- **Dynamic Price & Margin Monitor (`server/pricing_monitor.py`)**: Implemented via `compute_pricing_analysis()`, calculating exact unit economics, margin percentages, target pricing adjustments, competitor headroom opportunities, and undercutting defenses with multi-tier alerting (Critical, Warning, Opportunity, Healthy).
- **Quality & Invariants**:
  - `python -m flake8 server --count --select=E9,F63,F7,F82` returns `0` errors.
  - `python -m pytest tests/test_no_emojis.py` passes 100% (zero emojis across `server/` and `frontend/`).
  - Unit tests in `tests/test_ugc_reviews.py`, `tests/test_review_miner.py`, and `tests/test_price_monitor.py` pass 100%.

---

## 2. Feature Deep-Dive: Review Sentiment & UGC Drips (`server/reviews_ugc.py`)

### 2.1 Post-Purchase Review & UGC Drips (`generate_post_purchase_drip`)
- **Location**: `server/reviews_ugc.py:15-43`
- **Function Signature**: `generate_post_purchase_drip(product_name: str, brand_tone: str = "Warm and helpful", incentive: str = "15% off your next order") -> list`
- **Cadence & Strategy**:
  - **Step 1 (Day 3)**: *Delivery Check & Onboarding* — Unboxing confirmation, setup guide reference, direct reply prompt to solve immediate customer queries before friction builds.
  - **Step 2 (Day 7)**: *Review & Photo UGC Request* — 30-second honest review request, photo/video incentive coupon (`{incentive}`), direct review portal link.
  - **Step 3 (Day 14)**: *VIP Loyalty & Replenishment* — VIP referral pass offering reciprocal bonus rewards for the customer and a friend.

### 2.2 Sentiment Classification & Draft Replies (`classify_review_sentiment_and_reply`)
- **Location**: `server/reviews_ugc.py:45-90`
- **Classification Logic**:
  - Lexical parsing scans review text against `negative_signals` (`["broken", "terrible", "worst", "waste", "disappointed", "refund", "never", "hate", "awful", "scam", "poor"]`) and `positive_signals` (`["love", "great", "excellent", "perfect", "amazing", "best", "high quality", "fast", "awesome", "recommend"]`).
  - **Negative Category** (`rating <= 2` or `neg_count > pos_count`):
    - `sentiment`: `"negative"`
    - `status`: `"action_needed"`
    - `draft_reply`: Empathetic apology acknowledging `{product_name}`, commitment to quality, direct contact link to VIP support line offering immediate replacement or full refund.
  - **Neutral Category** (`rating == 3` and `neg_count <= pos_count`):
    - `sentiment`: `"neutral"`
    - `status`: `"action_needed"`
    - `draft_reply`: Grateful acknowledgment requesting specific feature feedback and improvement suggestions.
  - **Positive Category** (`rating >= 4` and `neg_count <= pos_count`):
    - `sentiment`: `"positive"`
    - `status`: `"published"`
    - `draft_reply`: Warm, celebratory thank-you recognizing glowing review and offering reward coupon for future orders.

### 2.3 API Endpoints & Schemas
- `POST /api/reviews/drip-templates` (`server/main.py:1055-1068`):
  - Request Model: `PostPurchaseDripRequest` (`product_name: str [2-200 chars]`, `brand_tone: Optional[str]`, `incentive_offer: Optional[str]`).
  - Response Model: `PostPurchaseDripResponse` (`id: str`, `product_name: str`, `drip_emails: list[dict]`).
- `POST /api/reviews/submit` (`server/main.py:1070-1117`):
  - Rate limited to 30/min; authenticated via API key/JWT.
  - Request Model: `CustomerReviewSubmitRequest` (`customer_name: str [1-100]`, `customer_email: Optional[str]`, `product_name: str [2-255]`, `rating: int [1-5]`, `review_text: str [5-5000]`).
  - Response Model: `CustomerReviewResponse`.
  - Database Model: `CustomerReview` (`server/database.py:229-242`) with `user_id` tenant isolation.
- `GET /api/reviews` (`server/main.py:1119-1137`):
  - Scoped to `CustomerReview.user_id == user.id`. Returns recent 100 customer reviews with sentiment tags and generated draft replies.

---

## 3. Feature Deep-Dive: 1-Star Competitor Review Flaw Miner (`server/ai_engine.py`)

### 3.1 Review Flaw Mining Engine (`mine_competitor_reviews`)
- **Location**: `server/ai_engine.py:303-361`
- **Function Signature**: `async def mine_competitor_reviews(product_name: str, competitor_name: str, reviews_text: str) -> dict`
- **Pipeline Workflow**:
  1. **Prompt Construction**: Ingests real 1-star and 2-star reviews of competitor products.
  2. **LLM Execution**: Dispatches prompt to OpenAI (`gpt-4o-mini`) or Gemini (`gemini-flash-latest`) via unified multi-provider client.
  3. **JSON Extraction**: Parses strict JSON output using regex-resilient `_extract_json_block()`.
  4. **Fallback Handling**: If AI key is missing or parsing fails, provides structured deterministic fallback response with clean baseline counter-copy.
  5. **Content Governance Filter**: Invokes `audit_generated_content()` (`server/ai_engine.py:360`) on the `counter_description` to scrub defamatory statements and unsupported claims.

### 3.2 Output Contract
Returns a structured dictionary matching `CompetitorMineResponse`:
- `extracted_flaws`: List of specific flaws and complaint clusters identified in the competitor reviews.
- `counter_description`: 100-150 word direct-response product description highlighting superiority and solving customer objections.
- `comparison_points`: Array of objects (`aspect`, `competitor_flaw`, `our_advantage`) forming a side-by-side comparison matrix.
- `ad_hooks`: Direct-response hook variations (call-out hook, Us vs. Them contrast hook, problem-awareness question).

### 3.3 Atomic Credit Invariant & Failure Refund
- **Location**: `server/main.py:851-894`
- **Atomic Balance Check & Deduction**:
  ```python
  updated = db.execute(
      text("UPDATE users SET generations = generations - 1 WHERE id = :uid AND generations >= 1"),
      {"uid": user.id}
  ).rowcount
  if updated == 0:
      raise HTTPException(status_code=402, detail="Insufficient generation balance. Please upgrade your plan.")
  ```
- **Guaranteed Refund on Upstream Error**:
  ```python
  except Exception as e:
      db.rollback()
      db.execute(text("UPDATE users SET generations = generations + 1 WHERE id = :uid"), {"uid": user.id})
      db.commit()
      logger.error("Competitor review mining failed: %s", e)
      raise HTTPException(status_code=500, detail="Review mining analysis failed. Your balance was refunded.")
  ```
- **Audit Persistence**: Serialized into `competitor_audits` table (`CompetitorAudit` model in `server/database.py:188-199`) under the merchant's `user_id`.

---

## 4. Feature Deep-Dive: Dynamic Competitor Price Monitoring & Alert Thresholds (`server/pricing_monitor.py`)

### 4.1 Unit Economics & Pricing Model (`compute_pricing_analysis`)
- **Location**: `server/pricing_monitor.py:10-59`
- **Function Signature**: `compute_pricing_analysis(cogs: float, selling_price: float, competitor_price: Optional[float] = None, target_margin: float = 40.0) -> Dict[str, Any]`
- **Mathematical Formulations**:
  - `profit_per_unit = round(selling_price - cogs, 2)`
  - `current_margin_pct = round((profit_per_unit / selling_price) * 100, 2)`
  - `target_price = round(cogs / (1 - (target_margin / 100)), 2)` (when `target_margin < 100`)

### 4.2 Status Health & Opportunity Alert Logic
| Condition | Status | Alert Classification & Actionable Guidance |
| :--- | :--- | :--- |
| `selling_price <= 0` | `critical` | Selling price invalid (must be greater than zero). |
| `current_margin_pct < 15.0%` | `critical` | Margin dangerously thin. Computes recommended price `$target_price` to hit target margin. |
| `current_margin_pct < target_margin` | `warning` | Margin below target. Recommends price adjustment `+$ (target_price - selling_price)`. |
| `competitor_price > selling_price * 1.12` | `healthy` | **Headroom Opportunity**: Computes safe increase `headroom_price = round(min(competitor_price * 0.95, selling_price * 1.15), 2)` to increase unit margin without surpassing competitor price. |
| `competitor_price < selling_price * 0.85` | `warning` | **Tactical Undercutting Alert**: Recommends defending margin with Review Miner counter-copy and bundle bonuses instead of engaging in a destructive price war. |
| Other cases | `healthy` | Gross margin aligned with target. |

### 4.3 REST Endpoints & Data Model
- `GET /api/pricing/items` (`server/main.py:1141-1147`): Lists all items tracked by `user_id`.
- `POST /api/pricing/item` (`server/main.py:1148-1200`): Creates or updates a SKU record (`PriceMarginItemCreate` schema), runs real-time pricing analysis, and updates DB record.
- `DELETE /api/pricing/item/{item_id}` (`server/main.py:1201-1211`): Scoped deletion preventing IDOR.
- `PriceMarginItem` Table (`server/database.py:244-259`): Stores `cogs_usd`, `selling_price_usd`, `competitor_price_usd`, `target_margin_pct`, `current_margin_pct`, `profit_per_unit_usd`, `status`, `recommendation`, and timestamp.

---

## 5. Quality, Governance & Invariant Verification Matrix

| Area | Requirement | Verification Status | Evidence / Verification Method |
| :--- | :--- | :--- | :--- |
| **Zero-Emoji Policy** | No Unicode emojis in server/frontend files | **PASS (100%)** | `pytest tests/test_no_emojis.py` passed; regex scan detected 0 emoji violations. |
| **Flake8 Linting** | 0 errors on `E9,F63,F7,F82` | **PASS (0 errors)** | `flake8 server --count --select=E9,F63,F7,F82` returned `0`. |
| **Multi-Tenant Isolation** | Scoped queries by `user_id == user.id` | **PASS** | Verified in `server/main.py` lines 1091, 1123, 1145, 1167, 1205. |
| **Atomic Quota Accounting** | Balance debit before AI call, refund on failure | **PASS** | Verified in `server/main.py:852-894` and `tests/test_review_miner.py:48-51`. |
| **Content Governance** | Anti-defamation & ungrounded claim filter | **PASS** | Verified in `server/ai_engine.py:360` with `audit_generated_content()`. |
| **Unit & Integration Tests** | All growth engine & pricing tests passing | **PASS (100%)** | `test_ugc_reviews.py`, `test_review_miner.py`, `test_price_monitor.py` all passing. |

---

## 6. Gaps, Edge Cases & Recommendations

1. **Brand Tone Customization in Review UGC Drips**:
   - *Observation*: `generate_post_purchase_drip()` in `server/reviews_ugc.py:15` accepts `brand_tone: str`, but the current 3-step templates use standard neutral copy.
   - *Recommendation*: While standard templates satisfy the requirements and pass all tests, an enhancement could inject tone modifiers or select tone-specific variant bodies (e.g., Casual, Luxury, Playful).
2. **Negative Rating Boundary in Classifier**:
   - *Observation*: Reviews with 1 or 2 stars are unconditionally categorized as `negative`, and reviews with `neg_count > pos_count` are also categorized as `negative`. 3-star reviews default to `neutral` with `action_needed`.
   - *Assessment*: This correctly handles edge cases such as a 5-star rating with negative text (e.g. sarcastic 5-star review), ensuring merchant follow-up.
3. **Price Monitor Zero COGS / Zero Selling Price**:
   - *Observation*: Handled defensively in `server/pricing_monitor.py:19-25` (`selling_price <= 0` returns `critical` error payload) and `tests/test_e2e_tiers.py:1808-1814` (`cogs=0.0` returns `100.0%` margin without division by zero error).
   - *Assessment*: Completely robust.
4. **Mock Patching Target for Competitor Review Miner**:
   - *Observation*: `server/main.py:845` does a local import `from .ai_engine import mine_competitor_reviews` inside the route handler. When unit tests mock this function, they must patch `server.ai_engine.mine_competitor_reviews` (as in `tests/test_review_miner.py:27`) rather than `server.main.mine_competitor_reviews`.
   - *Recommendation*: Documented for implementers and test authors to ensure patch targets align with local import patterns.

---

## 7. Conclusion

The Milestone 3 growth engine features assigned to Explorer 2 (Review Sentiment & UGC Drips, 1-Star Competitor Flaw Miner, and Dynamic Competitor Price Monitor) are complete, fully implemented, properly validated, and compliant with all project architectural standards.
