# Milestone 1 Specification Mining Report: Multi-Modal Campaign & Platform Schemas

**Author**: Spec Miner 1  
**Milestone**: Milestone 1 (Multi-Modal Campaign & Platform Schemas)  
**Date**: 2026-08-23  
**Target Scope**: F1, F2, F3, F4, F5, F6  

---

## Executive Summary
This report defines the comprehensive, authoritative specification for Milestone 1 of the KopyKat platform expansion. It covers the **Multi-Modal Vision Pipeline** (`server/campaigns.py`, `server/main.py:api_campaign_generate_vision`) and the **Multi-Platform Listing Optimization Engine** (`server/ai_engine.py`, `server/models.py`, `server/main.py:optimize_listing_endpoint`), detailing all Pydantic request/response models, exact field types and limits, prompt templates, deterministic offline fallbacks, entitlement checks, financial balance reservation/refund invariants, and zero-emoji compliance rules.

---

## Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Multi-Modal Vision | Omni-Channel Vision Campaign Generation (`/api/campaign/generate-vision`) | Accepts base64 product images, analyzes visual features via Gemini/OpenAI Vision, and produces a complete omni-channel marketing package (product title/description, SEO blog, 3-step email drip, social posts). | `image_base64: str` (min_length=10), `mime_type: Optional[str]` ("image/jpeg"), `keyword: Optional[str]`, `extra_context: Optional[str]` | `id: str` (UUID), `name: str` ("Vision Campaign: <detected_product_name>"), `assets: dict` containing `detected_product_name`, `detected_description`, `blog_post` (title, content), `email_drip` (3 items with subject, body), `social_posts` (3 items). | - HTTP 402 if generations balance < 1.<br>- HTTP 422 if image_base64 < 10 chars.<br>- HTTP 400 with full balance refund if base64 malformed or AI returns invalid JSON.<br>- HTTP 500 with full balance refund on unexpected AI failure. | `ORIGINAL_REQUEST.md §1`, `PROJECT.md §F1`, `server/campaigns.py`, `server/main.py:602`, `tests/test_campaigns.py` |
| 2 | Listing Optimization | Amazon Listing Schema & Optimizer (F2) | Generates A9/A10 search algorithm-compliant Amazon listing with keyword-packed title, 5 capitalized hook bullet points, backend search terms under 249 bytes, and structured HTML description. | `product_name: str` (2-255 chars), `platform: "amazon"`, `raw_details: str` (5-5000 chars), `keywords: Optional[str]`, `target_audience: Optional[str]`, `brand_persona: Optional[dict]` | `platform: "amazon"`, `product_name: str`, `optimized_title: str` (<200 chars), `bullet_points: list[str]` (exactly 5 items), `backend_search_terms: str` (<249 bytes, space-separated, no commas), `structured_description: str` (HTML `<p>`), `compliance_score: int` (90-99). | - HTTP 422 on schema violation.<br>- HTTP 403 if user lacks `marketplace_optimizer_pack` or `megastore` plan.<br>- Offline fallback returns deterministic compliant payload (score 95). | `ORIGINAL_REQUEST.md §1`, `PROJECT.md §F2`, `SCOPE.md §F2`, `server/ai_engine.py:378-393`, `tests/test_addons_monetization.py:39-54` |
| 3 | Listing Optimization | Shopify DTC Listing Schema & Optimizer (F3) | Generates DTC conversion-optimized Shopify listing with punchy H1 title, CTR meta description, 3-4 value proposition bullets, and rich HTML description with H2 benefit headings and guarantee policy. | `product_name: str`, `platform: "shopify"`, `raw_details: str`, `keywords: Optional[str]`, `target_audience: Optional[str]`, `brand_persona: Optional[dict]` | `platform: "shopify"`, `product_name: str`, `optimized_title: str` (<70 chars), `meta_description: str` (<155 chars), `bullet_points: list[str]` (3-4 items), `structured_description: str` (DTC HTML with `<h2>`, `<h3>`, `<ul>`), `compliance_score: int` (90-99). | - HTTP 422 on schema violation.<br>- HTTP 403 if user lacks entitlement.<br>- Offline fallback returns deterministic compliant payload (score 98). | `ORIGINAL_REQUEST.md §1`, `PROJECT.md §F3`, `SCOPE.md §F3`, `server/ai_engine.py:410-425`, `tests/test_addons_monetization.py:70-84` |
| 4 | Listing Optimization | Etsy Artisan Listing Schema & Optimizer (F4) | Generates handcrafted/artisan Etsy listing with comma/slash title, 13 long-tail tags (<20 chars each), 3-4 feature bullets (materials, dimensions, care), and warm story-driven description. | `product_name: str`, `platform: "etsy"`, `raw_details: str`, `keywords: Optional[str]`, `target_audience: Optional[str]`, `brand_persona: Optional[dict]` | `platform: "etsy"`, `product_name: str`, `optimized_title: str` (<140 chars), `tags: list[str]` (exactly 13 items, each <20 chars), `bullet_points: list[str]` (3-4 items), `structured_description: str` (warm story HTML), `compliance_score: int` (90-99). | - HTTP 422 on schema violation.<br>- HTTP 403 if user lacks entitlement.<br>- Offline fallback returns deterministic compliant payload (score 96). | `ORIGINAL_REQUEST.md §1`, `PROJECT.md §F4`, `SCOPE.md §F4`, `server/ai_engine.py:394-409`, `tests/test_addons_monetization.py:55-69` |
| 5 | Listing Optimization | TikTok Shop Listing Schema & Optimizer (F5) | Generates viral mobile-first TikTok Shop listing with viral hook title, 3 video script/hook teasers, 3-5 punchy bullets, 5-8 trending hashtags, and mobile description with strong call-to-action. | `product_name: str`, `platform: "tiktok"` or `"tiktok_shop"`, `raw_details: str`, `keywords: Optional[str]`, `target_audience: Optional[str]`, `brand_persona: Optional[dict]` | `platform: "tiktok"` / `"tiktok_shop"`, `product_name: str`, `optimized_title: str` (<100 chars), `short_hooks: list[str]` (3 video hooks), `bullet_points: list[str]` (3-5 items), `hashtags: list[str]` (5-8 items), `structured_description: str` (mobile HTML), `compliance_score: int` (90-99). | - HTTP 422 on schema violation.<br>- HTTP 403 if user lacks entitlement.<br>- Offline fallback returns deterministic compliant payload (score 97). | `ORIGINAL_REQUEST.md §1`, `PROJECT.md §F5`, `SCOPE.md §F5`, `server/models.py` |
| 6 | Listing Optimization | eBay Listing Schema & Optimizer (F6) | Generates high-conversion eBay listing with keyword-packed title (<80 chars), subtitle (<55 chars), structured Item Specifics dictionary, 3-4 feature bullets, and HTML template with shipping/payment/return policies. | `product_name: str`, `platform: "ebay"`, `raw_details: str`, `keywords: Optional[str]`, `target_audience: Optional[str]`, `brand_persona: Optional[dict]` | `platform: "ebay"`, `product_name: str`, `optimized_title: str` (<80 chars), `sub_title: str` (<55 chars), `item_specifics: dict[str, str]`, `bullet_points: list[str]` (3-4 items), `structured_description: str` (HTML listing template), `compliance_score: int` (90-99). | - HTTP 422 on schema violation.<br>- HTTP 403 if user lacks entitlement.<br>- Offline fallback returns deterministic compliant payload (score 96). | `ORIGINAL_REQUEST.md §1`, `PROJECT.md §F6`, `SCOPE.md §F6`, `server/models.py` |
| 7 | Monetization / Entitlement | Marketplace Optimizer Entitlement Gating | Restricts `/api/optimizer/marketplace-listing` to users who purchased the `marketplace_optimizer_pack` à-la-carte add-on or have the `megastore` plan. | Active User session, DB session | Allows endpoint execution if `user_has_entitlement(user, "marketplace_optimizer_pack", db)` evaluates to `True`. | Returns HTTP 403 Forbidden with `{"detail": "Marketplace Listing Optimizer Pack add-on or Megastore plan required"}`. | `tests/test_adversarial_hardening.py:263-276`, `server/main.py:1425-1427`, `server/billing.py` |
| 8 | Monetization / Persona | Brand Voice Persona Injection | Injects custom tone, voice guidelines, and rules from the user's `BrandPersona` table into listing optimizer prompts. | User's configured `BrandPersona` (brand_name, brand_voice_tone, rules_and_guidelines) | Prompt enriched with brand rules; output strictly aligns with tone. | Gracefully defaults to generic tone if no persona configured. | `tests/test_addons_monetization.py:15-38`, `server/ai_engine.py:427-429`, `server/main.py:1428-1436` |
| 9 | Quota Governance | Dual-Bucket Atomic Generation Reservation & Refund | Manages user generation quotas with dual buckets (monthly generations prioritized before purchased generations), row locking (`with_for_update` on non-sqlite), and atomic refund upon upstream AI failure. | `user_id: str`, `cost: int` | `(monthly_used: int, purchased_used: int)` | HTTP 402 if `generations < cost`. Reconciles corrupted balance totals automatically. | `PROJECT.md §4`, `server/main.py:320-360`, `tests/test_platform_hardening.py:68-83`, `tests/test_adversarial_hardening.py:297-321` |
| 10 | Quality Governance | Zero-Emoji Compliance Policy | System-wide invariant forbidding unicode emojis across all prompt templates, fallback strings, responses, and code files. | Any text generated by or contained within `server/` and `frontend/` | Plaintext / ASCII / sanitized UTF-8 strings with zero emoticons, symbols, pictographs, or emoji codepoints. | Test failure in `tests/test_no_emojis.py:test_zero_emojis_in_codebase`. | `tests/test_no_emojis.py`, `ORIGINAL_REQUEST.md §24`, `PROJECT.md §50` |

---

## Edge Cases

| # | Feature | Input | Observed / Expected Behavior |
|---|---------|-------|-----------------------------|
| 1 | Platform Enum Validation | `platform="walmart"` or `platform="instagram"` | Returns HTTP 422 Unprocessable Entity because platform regex strictly requires `^(amazon\|shopify\|etsy\|tiktok\|tiktok_shop\|ebay)$`. |
| 2 | Platform Alias Handling | `platform="tiktok"` vs `platform="tiktok_shop"` | Both match regex and resolve to the TikTok Shop optimizer logic and response schema. |
| 3 | Amazon Backend Keywords Byte Cap | Generated search terms > 249 bytes (UTF-8) | Prompt explicitly bounds search terms to <249 bytes without commas; fallback generator guarantees `<249` bytes (UTF-8 byte length test passes). |
| 4 | Amazon Title Character Cap | Product title > 200 characters | Prompt and fallback truncate / structure title strictly under 200 characters. |
| 5 | Etsy 13 Tags Length Cap | Tags list with items > 20 characters or count != 13 | Fallback and prompt enforce exactly 13 tags, each strictly under 20 characters (`all(len(t) < 20 for t in tags)` and `len(tags) == 13`). |
| 6 | Shopify Meta Description Cap | Meta description > 155 characters | Enforces `< 155` characters for SEO CTR compliance. |
| 7 | eBay Title and Subtitle Caps | eBay title > 80 chars or subtitle > 55 chars | Title strictly `< 80` chars (eBay search limit) and subtitle strictly `< 55` chars. |
| 8 | eBay Item Specifics Format | Item specifics input | Returned as a clean dictionary `dict[str, str]` (e.g. `{"Brand": "...", "Condition": "New", "Type": "..."}`). |
| 9 | TikTok Video Hooks | `short_hooks` generation | Returns array of exactly 3 video hooks/scripts (e.g., `["Stop doing X...", "Here is why...", "If you have X..."]`). |
| 10 | TikTok Hashtags | `hashtags` generation | Returns array of 5 to 8 trending hashtags (`5 <= len(hashtags) <= 8`), each starting with `#`. |
| 11 | Vision Base64 with Data URI Prefix | `image_base64="data:image/png;base64,iVBORw0KGgo..."` | `server/main.py` strips prefix before decoding (`raw_b64.split(",", 1)[1]`), correctly parsing the raw bytes. |
| 12 | Insufficient Generation Balance on Vision | User with `generations = 0` calls `/api/campaign/generate-vision` | Returns HTTP 402 Payment Required: `{"detail": "Insufficient campaigns remaining. Please upgrade your plan."}` without calling AI API. |
| 13 | AI Vision Provider Failure | Gemini/OpenAI API throws timeout or network error | Rollback database transaction, refund the deducted balance atomically to the user (`generations += 1`), and return HTTP 500 error message. |
| 14 | Missing Brand Persona | User has no `BrandPersona` record in database | Optimizer proceeds seamlessly using standard default copywriting guidelines without throwing NullPointer/AttributeError. |
| 15 | Free User without Entitlement | Free plan user calls `/api/optimizer/marketplace-listing` | Returns HTTP 403 Forbidden: `{"detail": "Marketplace Listing Optimizer Pack add-on or Megastore plan required"}`. |
| 16 | Zero Emojis in AI Prompts & Fallbacks | Fallback and prompt strings evaluated against emoji regex | All fallback text and prompt instructions contain 0 emojis, passing `test_no_emojis.py`. |

---

## Detailed Model & Interface Specifications

### 1. Pydantic Request Models (`server/models.py`)

#### `MarketplaceOptimizeRequest`
```python
class MarketplaceOptimizeRequest(BaseModel):
    product_name: str = Field(min_length=2, max_length=255)
    platform: str = Field(pattern="^(amazon|shopify|etsy|tiktok|tiktok_shop|ebay)$")
    raw_details: str = Field(min_length=5, max_length=5000)
    keywords: Optional[str] = None
    target_audience: Optional[str] = None
```

#### `MarketplaceOptimizeResponse`
```python
class MarketplaceOptimizeResponse(BaseModel):
    platform: str
    product_name: str
    optimized_title: str
    bullet_points: list[str] = []
    meta_description: Optional[str] = None
    backend_search_terms: Optional[str] = None
    tags: list[str] = []
    short_hooks: Optional[list[str]] = None
    hashtags: Optional[list[str]] = None
    sub_title: Optional[str] = None
    item_specifics: Optional[dict[str, str]] = None
    structured_description: str
    compliance_score: int  # 1-100 score on platform limits & keyword density
```

#### `CampaignVisionGenerateRequest`
```python
class CampaignVisionGenerateRequest(BaseModel):
    keyword: Optional[str] = ""
    extra_context: Optional[str] = ""
    image_base64: str = Field(min_length=10)
    mime_type: Optional[str] = "image/jpeg"
```

---

### 2. Platform Prompt & Fallback Rules (`server/ai_engine.py`)

#### Platform Specifications Matrix

| Platform | Title Constraints | Bullet Points | Specific Platform Fields | Description Format | Fallback Score |
|---|---|---|---|---|---|
| **Amazon** | < 200 chars; Brand + Product + Key Feature + Spec | Exactly 5 bullets; 2-4 word capitalized hook | `backend_search_terms`: < 249 bytes space-separated | Persuasive HTML `<p>...</p>` | 95 |
| **Shopify** | < 70 chars; Punchy H1 title | 3-4 bullets | `meta_description`: < 155 chars | DTC HTML with `<h2>`, `<h3>`, `<ul><li>` | 98 |
| **Etsy** | < 140 chars; Separated by commas/slashes | 3-4 bullets (materials, care, dimensions) | `tags`: exactly 13 long-tail tags, each < 20 chars | Warm story-driven HTML `<p>...</p>` | 96 |
| **TikTok Shop** | < 100 chars; (Viral Hook + Product + Benefit) | 3-5 punchy bullets | `short_hooks`: 3 video hook scripts;<br>`hashtags`: 5-8 hashtags (`#...`) | High-energy mobile description with CTA | 97 |
| **eBay** | < 80 chars; Search keyword-dense title | 3-4 bullets | `sub_title`: < 55 chars;<br>`item_specifics`: dict of 4-6 key/values | Complete HTML template with warranty/returns | 96 |

---

### 3. Endpoint Specifications

#### `POST /api/optimizer/marketplace-listing`
- **Authentication**: JWT Bearer or API Key (`auth: tuple = Depends(get_current_user_apikey)`)
- **Entitlement Check**: `user_has_entitlement(user, "marketplace_optimizer_pack", db)` (or Megastore plan) -> 403 Forbidden if not entitled.
- **Brand Persona Lookup**: Queries `BrandPersona` for `user.id`. If found, passes `{"brand_name": ..., "brand_voice_tone": ..., "rules_and_guidelines": ...}` to `optimize_marketplace_listing`.
- **Response**: `MarketplaceOptimizeResponse` containing all platform-specific fields.

#### `POST /api/campaign/generate-vision`
- **Authentication**: JWT Bearer or API Key
- **Rate Limit**: `@limiter.limit("5/minute")`
- **Quota Accounting**: Dual-bucket reservation `reserve_user_generations(user.id, 1, db)` before calling AI vision.
- **AI Processing**: Calls `generate_omni_campaign_from_image(image_bytes, mime_type, keyword, extra_context)`.
- **Failure Recovery**: On any exception, calls `refund_user_generations(user.id, monthly_used, purchased_used, db)` and rolls back DB.
- **Database Entry**: Inserts into `Campaign` table (`id=UUID`, `user_id=user.id`, `name="Vision Campaign: <detected_product_name>"`, `assets=json.dumps(...)`).
- **Response**: `{"id": cid, "name": name, "assets": data}`.

---

## Flake8 & Zero-Emoji Compliance Rules

1. **Flake8 Rule**: `python -m flake8 server --count --select=E9,F63,F7,F82` must return `0`.
2. **Zero-Emoji Rule**: `python -m pytest tests/test_no_emojis.py -v` must pass 100%. No emojis anywhere in strings, logs, fallbacks, or templates.

---

## Recommended Test Suite for Milestone 1

A dedicated unit test file `tests/test_marketplace_schemas.py` should be added to verify:
1. `test_amazon_schema_constraints`: Title < 200 chars, exactly 5 bullets, backend search terms < 249 bytes UTF-8, compliance_score >= 90.
2. `test_shopify_schema_constraints`: Title < 70 chars, meta_description < 155 chars, 3-4 bullets, DTC HTML, compliance_score >= 90.
3. `test_etsy_schema_constraints`: Title < 140 chars, exactly 13 tags all < 20 chars, compliance_score >= 90.
4. `test_tiktok_shop_schema_constraints`: Title < 100 chars, 3 short_hooks, 5-8 hashtags, 3-5 bullets, compliance_score >= 90.
5. `test_ebay_schema_constraints`: Title < 80 chars, subtitle < 55 chars, item_specifics dict, compliance_score >= 90.
6. `test_marketplace_optimizer_regex_rejection`: Platforms outside regex (e.g., "walmart", "target") raise 422.
7. `test_marketplace_optimizer_offline_fallbacks`: Direct call to `optimize_marketplace_listing` with all 5 platforms when no AI API keys are present returns fully compliant dicts.
8. `test_vision_campaign_dual_bucket_deduction_and_refund`: Quota reservation and refund invariants on `/api/campaign/generate-vision`.
