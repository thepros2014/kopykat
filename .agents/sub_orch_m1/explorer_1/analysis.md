# Milestone 1 Deep-Dive Analysis: Marketplace Listing Optimization & Platform Schemas

**Author**: Explorer 1 (Milestone 1 — Multi-Modal Campaign & Platform Schemas)  
**Date**: 2026-08-23  
**Target Files**: `server/models.py`, `server/ai_engine.py`, `server/main.py`, `tests/test_marketplace_schemas.py`

---

## 1. Executive Summary

A comprehensive audit of the marketplace listing optimization system (`server/ai_engine.py`, `server/models.py`, and `server/main.py`) was performed against the specifications defined in `PROJECT.md` and `SCOPE.md` (Features F2 through F6).

### Key Findings:
1. **Critical Gap — Missing Platforms**: TikTok Shop (`tiktok`, `tiktok_shop`) and eBay (`ebay`) are completely missing from `server/ai_engine.py` (both prompt generation and deterministic offline fallback).
2. **Critical Gap — Request Schema Regex Restriction**: `MarketplaceOptimizeRequest.platform` in `server/models.py:303` uses `pattern="^(amazon|etsy|shopify)$"`, strictly rejecting `tiktok`, `tiktok_shop`, and `ebay` with HTTP 422 errors. The required pattern is `^(amazon|shopify|etsy|tiktok|tiktok_shop|ebay)$`.
3. **Response Schema Gaps**: `MarketplaceOptimizeResponse` in `server/models.py:308-318` lacks fields required for TikTok Shop (`short_hooks`, `hashtags`) and eBay (`sub_title`, `item_specifics`).
4. **Shopify Fallback Defect**: In `server/ai_engine.py:486-490`, the deterministic fallback for Shopify generates only **3 bullet points** instead of the required **4 bullet points**.
5. **Character / Byte Constraint Enforcement**: Amazon backend search terms require strict `< 249 bytes (UTF-8)`. Title constraints for Amazon (< 200 chars), Shopify (< 70 chars), Etsy (< 140 chars), TikTok Shop (< 100 chars), and eBay (< 80 chars) need strict truncation/clamping in deterministic fallbacks.
6. **Zero-Emoji Policy Compliance**: All current fallback texts, prompts, and models comply with the zero-emoji invariant (verified by `test_no_emojis.py`). All proposed additions must strictly adhere to this invariant.

---

## 2. Platform-by-Platform Gap & Requirements Analysis

| Platform | Contract Key | Required Fields & Types | Character / Byte Constraints | Current Status in `ai_engine.py` | Gap / Defect |
|---|---|---|---|---|---|
| **Amazon** | `amazon` | `optimized_title`: str<br>`bullet_points`: list[str] (5)<br>`backend_search_terms`: str<br>`structured_description`: str (HTML)<br>`compliance_score`: int (90-99) | - Title: < 200 chars<br>- Bullets: Exactly 5, 2-4 word capitalized hook<br>- Backend Search Terms: < 249 bytes UTF-8 (space-separated, no commas, no repeats) | Implemented (Prompt & Fallback) | Minor: Ensure fallback title and backend search terms are clamped to 200 chars and 249 bytes. |
| **Shopify** | `shopify` | `optimized_title`: str<br>`meta_description`: str<br>`bullet_points`: list[str] (4)<br>`structured_description`: str (DTC HTML)<br>`compliance_score`: int (90-99) | - Title: < 70 chars (H1)<br>- Meta Description: < 155 chars<br>- Bullets: Exactly 4 key value props<br>- Description: H2 benefit headings & guarantee policy | Partial (Prompt & Fallback) | **Defect**: Fallback only has 3 bullets instead of 4. Title & meta desc must be clamped. |
| **Etsy** | `etsy` | `optimized_title`: str<br>`tags`: list[str] (13)<br>`bullet_points`: list[str] (3-4)<br>`structured_description`: str (Artisan HTML)<br>`compliance_score`: int (90-99) | - Title: < 140 chars (separated by commas/slashes)<br>- Tags: Exactly 13 long-tail tags, each < 20 chars<br>- Bullets: 3-4 feature highlights<br>- Description: Warm artisan story | Implemented (Prompt & Fallback) | Fallback meets tag counts and lengths. Ensure title clamped to 140 chars. |
| **TikTok Shop** | `tiktok`, `tiktok_shop` | `optimized_title`: str<br>`short_hooks`: list[str] (3)<br>`bullet_points`: list[str] (3-5)<br>`hashtags`: list[str] (5-8)<br>`structured_description`: str (Mobile HTML)<br>`compliance_score`: int (90-99) | - Title: < 100 chars (Viral hook + Product + Benefit)<br>- Hooks: 3 video script/hook teasers<br>- Hashtags: 5-8 trending tags<br>- Bullets: 3-5 punchy bullets | **Missing** | **Critical Gap**: No prompt branch, no fallback branch. Currently defaults to Shopify. |
| **eBay** | `ebay` | `optimized_title`: str<br>`sub_title`: str<br>`item_specifics`: dict<br>`bullet_points`: list[str] (3-4)<br>`structured_description`: str (HTML template)<br>`compliance_score`: int (90-99) | - Title: < 80 chars<br>- Subtitle: < 55 chars<br>- Item Specifics: Brand, MPN, Material, Condition, etc.<br>- Bullets: 3-4 feature/spec highlights<br>- Description: HTML template with policies | **Missing** | **Critical Gap**: No prompt branch, no fallback branch. Currently defaults to Shopify. |

---

## 3. Schema & Routing Analysis

### A. `server/models.py`
1. **`MarketplaceOptimizeRequest`**:
   - Current:
     ```python
     class MarketplaceOptimizeRequest(BaseModel):
         product_name: str = Field(min_length=2, max_length=255)
         platform: str = Field(pattern="^(amazon|etsy|shopify)$")
         raw_details: str = Field(min_length=5, max_length=5000)
         keywords: Optional[str] = None
         target_audience: Optional[str] = None
     ```
   - Change Required:
     Update regex to `pattern="^(amazon|shopify|etsy|tiktok|tiktok_shop|ebay)$"`.

2. **`MarketplaceOptimizeResponse`**:
   - Current:
     ```python
     class MarketplaceOptimizeResponse(BaseModel):
         platform: str
         product_name: str
         optimized_title: str
         bullet_points: list[str] = []
         meta_description: Optional[str] = None
         backend_search_terms: Optional[str] = None
         tags: list[str] = []
         structured_description: str
         compliance_score: int
     ```
   - Change Required: Add support for TikTok Shop and eBay output fields:
     ```python
     class MarketplaceOptimizeResponse(BaseModel):
         platform: str
         product_name: str
         optimized_title: str
         bullet_points: list[str] = []
         meta_description: Optional[str] = None
         backend_search_terms: Optional[str] = None
         tags: list[str] = []
         short_hooks: list[str] = []
         hashtags: list[str] = []
         sub_title: Optional[str] = None
         item_specifics: Optional[dict] = None
         structured_description: str
         compliance_score: int
     ```

### B. `server/main.py` (`/api/optimizer/marketplace-listing` endpoint)
- The endpoint constructor at line 1448 must populate the new fields from `res`:
  ```python
  return MarketplaceOptimizeResponse(
      platform=res.get("platform", body.platform),
      product_name=res.get("product_name", body.product_name),
      optimized_title=res.get("optimized_title", body.product_name),
      bullet_points=res.get("bullet_points", []),
      meta_description=res.get("meta_description"),
      backend_search_terms=res.get("backend_search_terms"),
      tags=res.get("tags", []),
      short_hooks=res.get("short_hooks", []),
      hashtags=res.get("hashtags", []),
      sub_title=res.get("sub_title") or res.get("subtitle"),
      item_specifics=res.get("item_specifics"),
      structured_description=res.get("structured_description", body.raw_details),
      compliance_score=res.get("compliance_score", 95)
  )
  ```

---

## 4. `server/ai_engine.py` Implementation Details

### A. Prompt Branching
In `optimize_marketplace_listing`:
- `amazon`: Prompt for 200-char title, 5 bullets with capitalized hooks, 249-byte search terms, compliance score 90-99.
- `shopify`: Prompt for 70-char title, 155-char meta description, 4 bullets, DTC HTML with H2 and guarantee policy, compliance score 90-99.
- `etsy`: Prompt for 140-char title, 13 long-tail tags (< 20 chars), 3-4 bullets, warm artisan story, compliance score 90-99.
- `tiktok` / `tiktok_shop`: Prompt for 100-char title (Viral hook + Product + Benefit), 3-5 punchy bullets, 3 video hooks/scripts (`short_hooks`), 5-8 trending hashtags (`hashtags`), mobile-first structured description, compliance score 90-99.
- `ebay`: Prompt for 80-char title, 55-char subtitle (`sub_title`), item specifics dictionary (`item_specifics`), 3-4 bullets, HTML listing template with policy sections (Overview, Specifications, Shipping, Returns/Warranty), compliance score 90-99.

### B. Fallback Branching & Clamping Logic
- **Amazon Fallback**:
  - `optimized_title`: `(f"{product_name} - Premium Quality with Maximum Durability")[:200]`
  - `bullet_points`: Exactly 5 hooks.
  - `backend_search_terms`: `f"{product_name.lower()} premium durable best high quality"[:248]`
  - `compliance_score`: `95`
- **Shopify Fallback**:
  - `optimized_title`: `(f"{product_name}")[:70]`
  - `meta_description`: `(f"Shop {product_name} with fast shipping and satisfaction guarantee. Discover superior quality today.")[:155]`
  - `bullet_points`: Exactly 4 bullets:
    1. `"Premium build and unmatched performance"`
    2. `"Fast direct-to-door fulfillment"`
    3. `"Hassle-free 30-day returns"`
    4. `"Dedicated customer support and 100% satisfaction commitment"`
  - `compliance_score`: `98`
- **Etsy Fallback**:
  - `optimized_title`: `(f"{product_name}, Handmade Custom Gift, Artisan Quality")[:140]`
  - `tags`: 13 items, all < 20 chars:
    `["handmade gift", "custom gift", "artisan quality", "unique home", "eco friendly", "personalized", "special gift", "holiday gift", "trending now", "handcrafted", "small batch", "best seller", "gift for her"]`
  - `bullet_points`: 3 items.
  - `compliance_score`: `96`
- **TikTok Shop Fallback**:
  - `optimized_title`: `(f"Must-Have: {product_name} for Everyday Excellence")[:100]`
  - `bullet_points`:
    1. `"Viral sensation engineered for high performance"`
    2. `"Sleek modern design that fits your aesthetic"`
    3. `"Unmatched quality at an unbeatable value"`
    4. `"Instant upgrade to your daily routine"`
  - `short_hooks`:
    1. `f"Stop scrolling! If you need {product_name}, you have to see this."`
    2. `f"Why everyone is obsessed with {product_name} on my feed."`
    3. `f"3 reasons why {product_name} is totally worth the hype."`
  - `hashtags`: `["#tiktokmademebuyit", "#viralproduct", "#musthave", "#trending", "#shopfinds", "#fyp"]`
  - `structured_description`: `f"<p><strong>Trending Now:</strong> {product_name}</p><p>{raw_details}</p><p>Grab yours before it sells out again!</p>"`
  - `compliance_score`: `96`
- **eBay Fallback**:
  - `optimized_title`: `(f"NEW {product_name} - Premium Quality Fast Shipping")[:80]`
  - `sub_title`: `(f"Authentic {product_name} with 100% Satisfaction Guarantee")[:55]`
  - `item_specifics`:
    `{"Brand": "Unbranded", "MPN": "Does Not Apply", "Condition": "New", "Type": "Standard", "Material": "Premium Quality"}`
  - `bullet_points`:
    1. `"Brand new condition in original retail packaging"`
    2. `"High quality construction designed for long-term use"`
    3. `"Fast and secure shipping with tracking number included"`
    4. `"30-day hassle-free returns on all orders"`
  - `structured_description`: `f"<div class='ebay-template'><h2>Product Overview</h2><p>{raw_details}</p><h2>Item Specifics</h2><ul><li>Condition: Brand New</li><li>Type: Premium</li></ul><h2>Shipping & Returns</h2><p>Ships within 24 hours. 30-day money-back guarantee.</p></div>"`
  - `compliance_score`: `95`

---

## 5. Proposed Code Changes (Handoff Artifacts)

### A. `server/models.py`
```python
# Lines 301-318
class MarketplaceOptimizeRequest(BaseModel):
    product_name: str = Field(min_length=2, max_length=255)
    platform: str = Field(pattern="^(amazon|shopify|etsy|tiktok|tiktok_shop|ebay)$")
    raw_details: str = Field(min_length=5, max_length=5000)
    keywords: Optional[str] = None
    target_audience: Optional[str] = None

class MarketplaceOptimizeResponse(BaseModel):
    platform: str
    product_name: str
    optimized_title: str
    bullet_points: list[str] = []
    meta_description: Optional[str] = None
    backend_search_terms: Optional[str] = None
    tags: list[str] = []
    short_hooks: list[str] = []
    hashtags: list[str] = []
    sub_title: Optional[str] = None
    item_specifics: Optional[dict] = None
    structured_description: str
    compliance_score: int  # 1-100 score on platform character limits & keyword density
```

### B. `server/ai_engine.py`
```python
async def optimize_marketplace_listing(
    product_name: str,
    platform: str,
    raw_details: str,
    keywords: Optional[str] = None,
    target_audience: Optional[str] = None,
    brand_persona: Optional[dict] = None
) -> dict:
    """
    Deep platform-specific listing optimizer for Amazon, Shopify, Etsy, TikTok Shop, and eBay.
    Complies strictly with character caps, keyword search placement, and conversion structures.
    """
    platform = platform.lower()
    
    # Platform-specific prompt logic
    if platform == "amazon":
        prompt = f"""You are an expert Amazon Listing Optimization Copywriter.
Optimize this product listing strictly following Amazon A9/A10 search algorithm guidelines.

Product: {product_name}
Raw Details: {raw_details}
Focus Keywords: {keywords or 'high converting search terms'}
Audience: {target_audience or 'general consumers'}

Return strictly JSON with keys:
- "optimized_title": keyword-rich title under 200 characters (Brand + Product + Key Feature + Size/Color/Pack)
- "bullet_points": array of exactly 5 benefit-driven bullet points (each starting with a 2-4 word capitalized hook)
- "backend_search_terms": space-separated search keywords under 249 bytes (no commas, no repeated words)
- "structured_description": persuasive product description with HTML breaks
- "compliance_score": integer 90-99
"""
    elif platform == "etsy":
        prompt = f"""You are an expert Etsy SEO and conversion specialist.
Optimize this handmade/artisan craft listing for Etsy's search engine.

Product: {product_name}
Raw Details: {raw_details}
Keywords: {keywords or 'artisan, gift, unique'}
Audience: {target_audience or 'gift shoppers and home decorators'}

Return strictly JSON with keys:
- "optimized_title": descriptive title under 140 characters separated by commas or slashes
- "tags": array of exactly 13 multi-word long-tail tags (each under 20 characters)
- "bullet_points": array of 3-4 feature highlights (materials, dimensions, care instructions)
- "structured_description": warm, story-driven product description
- "compliance_score": integer 90-99
"""
    elif platform in ("tiktok", "tiktok_shop"):
        prompt = f"""You are an expert TikTok Shop e-commerce and viral marketing copywriter.
Optimize this product listing for TikTok Shop conversions and creator video discovery.

Product: {product_name}
Raw Details: {raw_details}
Keywords: {keywords or 'trending viral product'}
Audience: {target_audience or 'social shoppers and impulse buyers'}

Return strictly JSON with keys:
- "optimized_title": punchy viral hook title under 100 characters (Viral Hook + Product + Benefit)
- "bullet_points": array of 3-5 punchy benefit bullet points
- "short_hooks": array of 3 creator video hooks/scripts (1-2 sentences each)
- "hashtags": array of 5-8 trending e-commerce hashtags (e.g., #tiktokmademebuyit, #viralproduct)
- "structured_description": mobile-optimized scannable product description with HTML breaks
- "compliance_score": integer 90-99
"""
    elif platform == "ebay":
        prompt = f"""You are an expert eBay SEO listing and conversion specialist.
Optimize this product listing for eBay Cassini search engine and high buyer trust.

Product: {product_name}
Raw Details: {raw_details}
Keywords: {keywords or 'fast shipping, quality guaranteed'}
Audience: {target_audience or 'online shoppers'}

Return strictly JSON with keys:
- "optimized_title": keyword-dense listing title strictly under 80 characters
- "sub_title": secondary subtitle under 55 characters
- "item_specifics": dictionary of key item specifics (Brand, MPN, Material, Condition, Type)
- "bullet_points": array of 3-4 feature and specification highlights
- "structured_description": professional HTML listing template including Overview, Specifications, Shipping, and Returns policy
- "compliance_score": integer 90-99
"""
    else:  # shopify
        prompt = f"""You are a Direct-to-Consumer (DTC) conversion rate optimization expert.
Optimize this Shopify product page for Google search ranking and high checkout conversion.

Product: {product_name}
Raw Details: {raw_details}
Keywords: {keywords or 'premium online store'}
Audience: {target_audience or 'ecommerce buyers'}

Return strictly JSON with keys:
- "optimized_title": clean, punchy H1 title under 70 characters
- "meta_description": high-CTR meta description under 155 characters
- "bullet_points": array of exactly 4 key value propositions
- "structured_description": rich DTC description with H2 benefit headings and guarantee policy
- "compliance_score": integer 90-99
"""

    if brand_persona:
        prompt += f"\n\nStrict Brand Voice Rules:\nBrand Name: {brand_persona.get('brand_name')}\nTone: {brand_persona.get('brand_voice_tone')}\nGuidelines: {brand_persona.get('rules_and_guidelines', '')}"

    prompt += "\n\nReturn ONLY valid JSON."

    try:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if api_key:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-flash-latest"))
            res = await model.generate_content_async(prompt)
            data = _extract_json_block(res.text.strip())
            if data:
                data["platform"] = platform
                data["product_name"] = product_name
                return data
    except Exception as e:
        logger.error("AI marketplace optimizer error: %s", e)

    # Deterministic fallback optimizer
    if platform == "amazon":
        return {
            "platform": "amazon",
            "product_name": product_name,
            "optimized_title": f"{product_name} - Premium Quality with Maximum Durability"[:200],
            "bullet_points": [
                "ENGINEERED FOR QUALITY: Built with premium materials to guarantee long lasting performance.",
                "EASY TO USE: Designed for effortless daily operation with zero hassle.",
                "VERSATILE APPLICATION: Perfect for home, office, or travel use.",
                "SATISFACTION GUARANTEED: Backed by our 30-day money-back guarantee.",
                "TRUSTED BRAND: Delivered with full customer support and satisfaction warranty."
            ],
            "backend_search_terms": f"{product_name.lower()} premium durable best high quality"[:248],
            "structured_description": f"<p>{raw_details}</p><p>Experience superior quality and design crafted for modern needs.</p>",
            "compliance_score": 95
        }
    elif platform == "etsy":
        return {
            "platform": "etsy",
            "product_name": product_name,
            "optimized_title": f"{product_name}, Handmade Custom Gift, Artisan Quality"[:140],
            "tags": ["handmade gift", "custom gift", "artisan quality", "unique home", "eco friendly", "personalized", "special gift", "holiday gift", "trending now", "handcrafted", "small batch", "best seller", "gift for her"],
            "bullet_points": [
                "Handcrafted with care using premium materials",
                "Carefully packaged in sustainable packaging",
                "Fast shipping and responsive customer support"
            ],
            "structured_description": f"<p>{raw_details}</p><p>Each piece is thoughtfully crafted by hand to ensure exceptional detail and character.</p>",
            "compliance_score": 96
        }
    elif platform in ("tiktok", "tiktok_shop"):
        return {
            "platform": platform,
            "product_name": product_name,
            "optimized_title": f"Must-Have: {product_name} for Everyday Excellence"[:100],
            "bullet_points": [
                "Viral sensation engineered for high performance",
                "Sleek modern design that fits your aesthetic",
                "Unmatched quality at an unbeatable value",
                "Instant upgrade to your daily routine"
            ],
            "short_hooks": [
                f"Stop scrolling! If you need {product_name}, you have to see this.",
                f"Why everyone is obsessed with {product_name} on my feed.",
                f"3 reasons why {product_name} is totally worth the hype."
            ],
            "hashtags": ["#tiktokmademebuyit", "#viralproduct", "#musthave", "#trending", "#shopfinds", "#fyp"],
            "structured_description": f"<p><strong>Trending Now:</strong> {product_name}</p><p>{raw_details}</p><p>Grab yours before it sells out again!</p>",
            "compliance_score": 96
        }
    elif platform == "ebay":
        return {
            "platform": "ebay",
            "product_name": product_name,
            "optimized_title": f"NEW {product_name} - Premium Quality Fast Shipping"[:80],
            "sub_title": f"Authentic {product_name} with 100% Satisfaction Guarantee"[:55],
            "item_specifics": {
                "Brand": "Unbranded",
                "MPN": "Does Not Apply",
                "Condition": "New",
                "Type": "Standard",
                "Material": "Premium Quality"
            },
            "bullet_points": [
                "Brand new condition in original retail packaging",
                "High quality construction designed for long-term use",
                "Fast and secure shipping with tracking number included",
                "30-day hassle-free returns on all orders"
            ],
            "structured_description": f"<div class='ebay-template'><h2>Product Overview</h2><p>{raw_details}</p><h2>Item Specifics</h2><ul><li>Condition: Brand New</li><li>Type: Premium</li></ul><h2>Shipping & Returns</h2><p>Ships within 24 hours. 30-day money-back guarantee.</p></div>",
            "compliance_score": 95
        }
    else:  # shopify
        return {
            "platform": "shopify",
            "product_name": product_name,
            "optimized_title": f"{product_name}"[:70],
            "meta_description": f"Shop {product_name} with fast shipping and satisfaction guarantee. Discover superior quality today."[:155],
            "bullet_points": [
                "Premium build and unmatched performance",
                "Fast direct-to-door fulfillment",
                "Hassle-free 30-day returns",
                "Dedicated customer support and 100% satisfaction commitment"
            ],
            "structured_description": f"<h2>Why Choose {product_name}</h2><p>{raw_details}</p><h3>Key Advantages</h3><ul><li>High grade materials</li><li>Exceptional comfort and function</li></ul>",
            "compliance_score": 98
        }
```

### C. `server/main.py`
```python
    return MarketplaceOptimizeResponse(
        platform=res.get("platform", body.platform),
        product_name=res.get("product_name", body.product_name),
        optimized_title=res.get("optimized_title", body.product_name),
        bullet_points=res.get("bullet_points", []),
        meta_description=res.get("meta_description"),
        backend_search_terms=res.get("backend_search_terms"),
        tags=res.get("tags", []),
        short_hooks=res.get("short_hooks", []),
        hashtags=res.get("hashtags", []),
        sub_title=res.get("sub_title") or res.get("subtitle"),
        item_specifics=res.get("item_specifics"),
        structured_description=res.get("structured_description", body.raw_details),
        compliance_score=res.get("compliance_score", 95)
    )
```

---

## 6. Verification Strategy & Test Cases

Recommended unit test suite in `tests/test_marketplace_schemas.py`:
1. **Amazon Schema Verification**:
   - Title length < 200
   - Exactly 5 bullet points
   - Backend search terms UTF-8 bytes < 249
   - Compliance score >= 90
2. **Shopify Schema Verification**:
   - Title length < 70
   - Meta description < 155
   - Exactly 4 bullet points
   - DTC structured HTML description
   - Compliance score >= 90
3. **Etsy Schema Verification**:
   - Title length < 140
   - Exactly 13 tags, each tag length < 20
   - 3-4 bullet points
   - Compliance score >= 90
4. **TikTok Shop Schema Verification**:
   - Tests both `"tiktok"` and `"tiktok_shop"`
   - Title length < 100
   - Exactly 3 video short hooks
   - 5-8 hashtags
   - 3-5 punchy bullets
   - Compliance score >= 90
5. **eBay Schema Verification**:
   - Title length < 80
   - Subtitle length < 55
   - Item specifics dictionary containing Brand, MPN, Condition, Type, Material
   - 3-4 bullet points
   - HTML template with policy sections
   - Compliance score >= 90
6. **Regex Pattern & Rejection Test**:
   - Valid platforms: `amazon`, `shopify`, `etsy`, `tiktok`, `tiktok_shop`, `ebay` pass with 200 OK.
   - Invalid platforms: `walmart`, `temu`, `aliexpress`, `foo` rejected with 422 Unprocessable Entity.
7. **Zero-Emoji Enforcement**:
   - Verify zero emojis across all output fields for all 5 platforms.
