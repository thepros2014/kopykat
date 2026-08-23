# Analysis: Multi-Modal Vision Pipeline & Campaign Generation

**Milestone**: Milestone 1 (Multi-Modal Campaign & Platform Schemas)  
**Agent**: Explorer 2 (`sub_orch_m1/explorer_2`)  
**Date**: 2026-08-23  

---

## 1. Executive Summary

This report provides a comprehensive technical investigation of the **Multi-Modal Vision Pipeline** and **Campaign Endpoints** in the KopyKat platform, specifically analyzing:
- `server/campaigns.py`: Multi-modal vision analysis (`generate_omni_campaign_from_image`), omni campaign generation (`generate_omni_campaign`), demo generation (`generate_demo_campaign`), and social signal scraping (`scrape_pain_points`).
- `server/main.py`: `POST /api/campaign/generate-vision`, `POST /api/campaign/generate`, `POST /api/campaign/push`, and `POST /api/public/demo`.
- `server/models.py`: Pydantic validation schemas for vision requests (`CampaignVisionGenerateRequest`).
- Quota accounting, dual-bucket model (`monthly_generations` / `purchased_generations`), atomic reservation/refund invariants, deterministic offline fallbacks, and zero-emoji compliance.

---

## 2. Architecture & File Overview

| Component | File Path | Primary Responsibilities |
|---|---|---|
| **Vision & Omni Campaigns** | `server/campaigns.py` | Vision analysis with Gemini / OpenAI, multi-modal prompt construction, structured omni-channel output generation (blog, emails, social), social pain point simulation |
| **API Endpoints** | `server/main.py` (lines 578–675) | Route handlers for `/api/campaign/generate`, `/api/campaign/generate-vision`, `/api/campaign/push`, `/api/public/demo`, quota accounting |
| **Pydantic Schemas** | `server/models.py` (lines 157–162) | `CampaignVisionGenerateRequest`, `CampaignGenerateRequest`, `CampaignPushRequest` |
| **Database Models** | `server/database.py` (lines 91–115) | `Campaign`, `PushJob`, `User`, `UsageRecord` |
| **Content Governance** | `server/content_governance.py` | Anti-defamation and claims compliance filters |

---

## 3. Deep-Dive Findings by Area

### 3.1 Multi-Modal Vision Pipeline (`server/campaigns.py`)

#### A. Prompt Engineering & Output Structure
In `generate_omni_campaign_from_image(image_bytes: bytes, mime_type: str, keyword: str = "", extra_context: str = "") -> dict`:
- **Role Persona**: Elite direct-response marketer, product catalog specialist, and copywriter.
- **Input Context**: Product image bytes + MIME type, target keyword/category, extra user context, and scraped pain points.
- **Strict Output Schema**:
  ```json
  {
    "detected_product_name": "Accurate, marketable product title (5-10 words)",
    "detected_description": "Detailed, benefit-rich product description (100-150 words)",
    "blog_post": {
      "title": "A catchy, SEO-optimized title",
      "content": "Full blog post in clean HTML format with <h2>, <h3>, <p>, <ul>."
    },
    "email_drip": [
      {
        "subject": "Email 1 Subject (Hook & Problem Awareness)",
        "body": "HTML body for email 1 using PAS framework."
      },
      {
        "subject": "Email 2 Subject (Social Proof & Benefits)",
        "body": "HTML body for email 2."
      },
      {
        "subject": "Email 3 Subject (Urgency & Direct Call to Action)",
        "body": "HTML body for email 3."
      }
    ],
    "social_posts": [
      "Engaging Instagram/Facebook product post with hashtags",
      "Punchy Twitter/X post highlighting key transformation",
      "Professional LinkedIn/Pinterest product highlight"
    ]
  }
  ```

#### B. Multi-Provider Vision Model Execution
The engine supports both Google Gemini Vision and OpenAI Vision:
1. **Google Gemini Vision**:
   - Model: `os.environ.get('GEMINI_MODEL', 'gemini-1.5-flash')`.
   - Invocation: `model.generate_content([{"mime_type": mime_type or "image/jpeg", "data": image_bytes}, prompt])`.
   - Preferred when `AI_PROVIDER == 'gemini'` or when `GEMINI_API_KEY` is present and `OPENAI_API_KEY` is absent.
2. **OpenAI Vision**:
   - Model: `os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')`.
   - Invocation: Converts `image_bytes` to base64 data URI (`data:{mime_type};base64,{b64_img}`) and sends via `client.chat.completions.create(..., response_format={"type": "json_object"})`.
3. **Provider Fallback**:
   - If Gemini Vision fails with an exception and `OPENAI_API_KEY` is present, it logs a warning and falls back to OpenAI Vision.

#### C. Parsing Resilience & JSON Extraction
- `_extract_clean_json(text: str)` strips leading/trailing markdown code blocks (` ```json `, ` ``` `).
- **Vulnerability**: Unlike `_extract_json_block` in `server/ai_engine.py`, `_extract_clean_json` in `server/campaigns.py` lacks a regex fallback (`re.search(r'\{.*\}', clean_text, re.DOTALL)`). If an LLM includes introductory text before the markdown fence or trailing explanatory text, `json.loads` will raise `JSONDecodeError`.

---

### 3.2 Payload Handling & Image Ingestion

#### A. Base64 Handling in `POST /api/campaign/generate-vision`
- Model schema: `CampaignVisionGenerateRequest` (`image_base64: str = Field(min_length=10)`, `mime_type: Optional[str] = "image/jpeg"`, `keyword: Optional[str] = ""`, `extra_context: Optional[str] = ""`).
- Ingestion logic in `server/main.py`:
  ```python
  raw_b64 = body.image_base64
  if "," in raw_b64:
      raw_b64 = raw_b64.split(",", 1)[1]
  img_bytes = base64.b64decode(raw_b64)
  ```
- **Strengths**: Successfully handles both pure base64 strings and Data URI formats (e.g. `data:image/png;base64,...`).
- **Gaps / Weaknesses**:
  1. `CampaignVisionGenerateRequest` only accepts `image_base64`; it does not accept `image_url`. If remote image ingestion is needed, clients must download and encode to base64 client-side.
  2. If `image_base64` has invalid characters or padding, `base64.b64decode` raises `binascii.Error` or `ValueError`.

---

### 3.3 Quota Reservation & Refund Invariants

#### Critical Bug in `POST /api/campaign/generate-vision` (`server/main.py:619–656`)

In `POST /api/campaign/generate` (lines 586–600), quota reservation is handled correctly:
```python
monthly_used, purchased_used = reserve_user_generations(user.id, 1, db)
try:
    ...
except ValueError as e:
    refund_user_generations(user.id, monthly_used, purchased_used, db)
    raise HTTPException(status_code=400, detail=str(e))
except Exception:
    refund_user_generations(user.id, monthly_used, purchased_used, db)
    raise HTTPException(status_code=500, detail="Generation failed...")
```

However, in `POST /api/campaign/generate-vision` (lines 619–656), the code directly executes raw SQL:
```python
# Invariant: Atomic credit deduction before expensive Vision generation
updated = db.execute(
    text("UPDATE users SET generations = generations - 1 WHERE id = :uid AND generations >= 1"),
    {"uid": user.id}
).rowcount
if updated == 0:
    raise HTTPException(status_code=402, detail="Insufficient campaigns remaining. Please upgrade your plan.")

try:
    ...
except ValueError as e:
    db.rollback()
    # Refund on input/AI parsing failure
    db.execute(text("UPDATE users SET generations = generations + 1 WHERE id = :uid"), {"uid": user.id})
    db.commit()
    raise HTTPException(status_code=400, detail=str(e))
except Exception as e:
    db.rollback()
    db.execute(text("UPDATE users SET generations = generations + 1 WHERE id = :uid"), {"uid": user.id})
    db.commit()
    raise HTTPException(status_code=500, detail="Vision generation failed...")
```

#### Defects Identified in `/api/campaign/generate-vision`:
1. **Dual-Bucket Desynchronization**: Directly decrementing `users.generations` leaves `users.monthly_generations` and `users.purchased_generations` untouched. This violates the dual-bucket invariant `monthly_generations + purchased_generations == generations` (PROJECT.md §F17).
2. **Infinite Credit Generation Exploit (Critical Financial Bug)**:
   - When an uncommitted `UPDATE users SET generations = generations - 1` is run in an open transaction, and an exception occurs, `db.rollback()` cancels the initial decrement (resetting the balance in the database to its starting value).
   - Then, the exception handler executes `UPDATE users SET generations = generations + 1` and calls `db.commit()`.
   - **Result**: The user is awarded +1 credit on every failed request! An attacker can artificially inflate their balance by sending invalid payloads.
3. **Fix Requirement**: Replace the raw SQL updates with centralized helper functions:
   ```python
   monthly_used, purchased_used = reserve_user_generations(user.id, 1, db)
   try:
       ...
   except ValueError as e:
       refund_user_generations(user.id, monthly_used, purchased_used, db)
       raise HTTPException(status_code=400, detail=str(e))
   except Exception as e:
       refund_user_generations(user.id, monthly_used, purchased_used, db)
       raise HTTPException(status_code=500, detail="Vision generation failed due to an internal error. Your balance was refunded.")
   ```

---

### 3.4 Deterministic Offline Fallback Handling

#### Current State in `server/campaigns.py`:
- `generate_omni_campaign`, `generate_demo_campaign`, and `generate_omni_campaign_from_image` have **NO deterministic offline fallbacks**.
- If `GEMINI_API_KEY` and `OPENAI_API_KEY` are not configured, or if LLM calls fail during network outages/rate-limiting, `generate_omni_campaign_from_image` raises `ValueError`.
- In unit testing, tests are forced to mock `server.campaigns.generate_omni_campaign_from_image` explicitly (as seen in `tests/test_campaigns.py`).

#### Comparison with `server/ai_engine.py`:
- `server/ai_engine.py` provides deterministic offline fallbacks for all marketplace listings (`amazon`, `shopify`, `etsy`, `tiktok`, `ebay`), allowing endpoints to return compliant schemas even when offline or unconfigured.

#### Recommendation for `server/campaigns.py`:
Implement a deterministic fallback inside `generate_omni_campaign_from_image`:
```python
def _generate_fallback_vision_campaign(keyword: str, extra_context: str) -> dict:
    title = f"{keyword.title() if keyword else 'Premium Artisan Product'}"
    return {
        "detected_product_name": title,
        "detected_description": f"Engineered for superior reliability and modern aesthetics, this {keyword or 'product'} combines durable materials with elegant ergonomics for everyday excellence.",
        "blog_post": {
            "title": f"Why the {title} is Transforming the Industry",
            "content": f"<h2>Modern Innovation Meets Timeless Design</h2><p>In today's fast-paced market, consumers demand reliability without compromise. The {title} delivers on every front.</p><h3>Key Highlights</h3><ul><li>Precision craftsmanship and premium build</li><li>Effortless operation and seamless workflow</li><li>Backed by comprehensive quality guarantee</li></ul>"
        },
        "email_drip": [
            {
                "subject": f"Are you struggling with standard {keyword or 'products'}?",
                "body": f"<p>Most solutions in the market fail when you need them most. Discover how {title} solves the common frustration with proven performance.</p>"
            },
            {
                "subject": f"Why top creators choose {title}",
                "body": f"<p>See how our customers transformed their results within the first 30 days of using {title}.</p>"
            },
            {
                "subject": f"Exclusive offer: Upgrade to {title} today",
                "body": f"<p>Claim your 30-day satisfaction guarantee and experience the difference today.</p>"
            }
        ],
        "social_posts": [
            f"Upgrade your routine with {title}. Premium craftsmanship designed for high performance. #ecommerce #quality #innovation",
            f"Tired of fragile alternatives? {title} provides durable excellence you can trust every day.",
            f"Discover why {title} is becoming the go-to standard for industry professionals."
        ]
    }
```

---

### 3.5 Zero-Emoji Policy Compliance

#### Findings:
1. **Source Code & Prompts**: Verified that `server/campaigns.py` and `server/main.py` contain zero emojis.
2. **Automated Verification**: `tests/test_no_emojis.py` runs against all `.py`, `.html`, `.js`, `.css`, and `.json` files in `server/` and `frontend/` using a comprehensive Unicode regex covering Emoticons, Pictographs, Transport symbols, Flags, Dingbats, and Replacement chars (`\ufffd`).
3. **Test Status**: Passed (100% compliant).
4. **Prompt Guardrail**: AI prompts in `server/campaigns.py` must avoid requesting emojis in social posts (e.g. replacing emoji hooks with strong textual hooks).

---

## 4. Summary of Invariant Checks & Recommendations

| Invariant / Requirement | Current Status | Assessment | Recommended Action |
|---|---|---|---|
| **Dual-Bucket Quota Reservation** | Broken in `/api/campaign/generate-vision` | High Risk (Raw SQL bypass & transaction rollback bug causes credit inflation) | Refactor to use `reserve_user_generations(user.id, 1, db)` and `refund_user_generations` |
| **Deterministic Offline Fallback** | Absent in `server/campaigns.py` | Medium Risk (Raises ValueError if API keys absent) | Add `_generate_fallback_vision_campaign` |
| **Multi-Provider Vision (Gemini/OpenAI)** | Implemented with Gemini -> OpenAI fallback | Good | Improve JSON parsing with regex fallback (`_extract_json_block`) |
| **Zero-Emoji Policy** | Fully Compliant | Passed | Ensure prompts and fallback copy contain zero emojis |
| **Async / Event-Loop Safety** | Synchronous I/O in async route | Minor Performance Concern | Wrap synchronous AI generation in `asyncio.to_thread` or make async |

---

## 5. Proposed Code Fixes

### A. Fix for `server/main.py` (`api_campaign_generate_vision`)
```python
@app.post("/api/campaign/generate-vision", tags=["Campaigns"])
@limiter.limit("5/minute")
async def api_campaign_generate_vision(
    request: Request,
    body: CampaignVisionGenerateRequest,
    auth: tuple = Depends(get_current_user_apikey),
    db: Session = Depends(get_db)
):
    from .database import Campaign
    from .campaigns import generate_omni_campaign_from_image
    import uuid
    import json
    import base64
    
    user, _ = auth
    
    # Invariant: Atomic dual-bucket credit deduction before expensive Vision generation
    monthly_used, purchased_used = reserve_user_generations(user.id, 1, db)
        
    try:
        raw_b64 = body.image_base64
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(raw_b64)
        
        data = generate_omni_campaign_from_image(
            image_bytes=img_bytes,
            mime_type=body.mime_type or "image/jpeg",
            keyword=body.keyword or "",
            extra_context=body.extra_context or ""
        )
        
        cid = str(uuid.uuid4())
        prod_title = data.get("detected_product_name", body.keyword or "Product")
        name = f"Vision Campaign: {prod_title}"
        
        db.add(Campaign(id=cid, user_id=user.id, name=name, assets=json.dumps(data)))
        db.commit()
        return {"id": cid, "name": name, "assets": data}
    except ValueError as e:
        refund_user_generations(user.id, monthly_used, purchased_used, db)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        refund_user_generations(user.id, monthly_used, purchased_used, db)
        raise HTTPException(status_code=500, detail="Vision generation failed due to an internal error. Your balance was refunded.")
```

### B. Fix for `server/campaigns.py` (`generate_omni_campaign_from_image`)
Enhance `_extract_clean_json` with regex fallback and add deterministic offline fallback when no AI keys are present.
