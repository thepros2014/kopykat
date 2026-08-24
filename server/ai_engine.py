from .content_governance import audit_generated_content
import logging
logger = logging.getLogger(__name__)
"""
ai_engine.py - AI content generation.
Supports OpenAI GPT-4o and Google Gemini. Falls back automatically.
"""

import os
import time
import uuid
import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session
import re

def _extract_json_block(text: str) -> dict:
    """Extracts JSON object from LLM response with regex matching and error resilience."""
    clean_text = text.strip()
    if clean_text.startswith("```json"):
        clean_text = clean_text[7:]
    if clean_text.startswith("```"):
        clean_text = clean_text[3:]
    if clean_text.endswith("```"):
        clean_text = clean_text[:-3]
    clean_text = clean_text.strip()
    
    try:
        return json.loads(clean_text)
    except Exception:
        match = re.search(r'\{.*\}', clean_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        return {}


EMOJI_PATTERN = re.compile(
    r"[\U0001F600-\U0001F64F"
    r"\U0001F300-\U0001F5FF"
    r"\U0001F680-\U0001F6FF"
    r"\U0001F1E0-\U0001F1FF"
    r"\U0001F900-\U0001F9FF"
    r"\U0001FA70-\U0001FAFF"
    r"\U00002702-\U000027B0"
    r"\U000024C2-\U0001F251"
    r"\U00002600-\U000026FF"
    r"\U00002B50"
    r"\U0000FE0F"
    r"\ufffd"
    r"]+",
    flags=re.UNICODE
)

def _strip_emojis(text: str) -> str:
    if not isinstance(text, str):
        return text
    return EMOJI_PATTERN.sub("", text).strip()


from .database import UsageRecord

#  Config 

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY  = os.getenv("GEMINI_API_KEY", "")
AI_PROVIDER     = os.getenv("AI_PROVIDER", "openai").lower()   # "openai" or "gemini"
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GEMINI_MODEL    = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

# Cost per 1K tokens in USD (approximate)
COST_PER_1K = {
    "gpt-4o-mini": 0.00015,
    "gpt-4o":      0.005,
    "gemini-1.5-flash": 0.000075,
    "gemini-1.5-pro":   0.00125,
}

#  Prompt templates for each copy type 

PROMPTS = {
    "product_description": (
        "Write {variations} compelling product description(s). "
        "Use the AIDA framework (Attention, Interest, Desire, Action). "
        "Focus heavily on benefits and transformation rather than just features. Keep under 150 words each.\n\n"
        "Product/Context: {context}\n\nTone: {tone}"
    ),
    "email_subject": (
        "Write {variations} email subject line(s) optimized for maximum open rates. "
        "Utilize curiosity gaps, urgency, or personalization. Keep them punchy (under 50 characters ideally).\n\n"
        "Context: {context}\n\nTone: {tone}"
    ),
    "email_body": (
        "Write {variations} persuasive marketing email body/bodies. "
        "Use the PAS framework (Problem, Agitation, Solution). Make paragraphs extremely short (1-2 sentences) "
        "for high scannability. End with a singular, clear Call to Action.\n\n"
        "Context: {context}\n\nTone: {tone}"
    ),
    "social_post": (
        "Write {variations} engaging social media post(s) designed to stop the scroll. "
        "Start with a strong hook, provide value or a bold claim, and end with a high-converting CTA.\n\n"
        "Context: {context}\n\nTone: {tone}"
    ),
    "ad_headline": (
        "Write {variations} high-converting ad headline(s). Maximum 10 words each. "
        "Focus on the primary pain point or the ultimate dream outcome. Make it irresistible.\n\n"
        "Context: {context}\n\nTone: {tone}"
    ),
    "ad_body": (
        "Write {variations} persuasive ad copy body/bodies. "
        "Overcome a key objection immediately, highlight the primary benefit, and drive urgency to click.\n\n"
        "Context: {context}\n\nTone: {tone}"
    ),
    "landing_page_hero": (
        "Write {variations} landing page hero section(s). Format each exactly like this:\n"
        "Headline: [Punchy benefit-driven headline]\n"
        "Subheadline: [Supporting context that handles objections]\n"
        "CTA: [Action-oriented button text]\n\n"
        "Context: {context}\n\nTone: {tone}"
    ),
    "call_to_action": (
        "Write {variations} powerful call-to-action button text(s). Limit to 2-6 words each. "
        "Use action verbs and focus on the value the user gets by clicking (e.g., 'Get My Free Plan' instead of 'Submit').\n\n"
        "Context: {context}\n\nTone: {tone}"
    ),
    "seo_meta_description": (
        "Write {variations} SEO meta description(s) strictly under 155 characters. "
        "Include the primary keyword naturally and create a strong reason to click the search result.\n\n"
        "Context: {context}"
    ),
    "blog_intro": (
        "Write {variations} captivating blog post introduction(s) (100-150 words). "
        "Use the APP method (Agree, Promise, Preview) to hook the reader immediately.\n\n"
        "Topic/Context: {context}\n\nTone: {tone}"
    ),
}

SYSTEM_PROMPT = (
    "You are KopyKat, an elite, world-class direct-response copywriter. "
    "You write high-converting copy that drives sales. "
    "CRITICAL INSTRUCTION: You MUST output your response strictly as a JSON object with a single key 'variations' which is an array of strings. "
    "Do NOT wrap the JSON in markdown code blocks. Do NOT output any conversational text. "
    "Example format: {\"variations\": [\"variation 1 text\", \"variation 2 text\"]}"
)


#  OpenAI generation 

async def _generate_openai(prompt: str, max_tokens: int) -> tuple[str, int]:
    """Returns (text, tokens_used)."""
    try:
        from .openai_client import generate_text_async

        return await generate_text_async(
            api_key=OPENAI_API_KEY,
            model=OPENAI_MODEL,
            input_value=prompt,
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=max_tokens,
            temperature=0.8,
            json_mode=True,
        )
    except Exception as e:
        raise RuntimeError(f"OpenAI error: {e}")


#  Gemini generation 

async def _generate_gemini(prompt: str, max_tokens: int) -> tuple[str, int]:
    """Returns (text, tokens_used). Gemini token counts are estimated."""
    try:
        from .gemini_client import generate_content_async

        response = await generate_content_async(
            api_key=GEMINI_API_KEY,
            model=GEMINI_MODEL,
            contents=prompt,
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=max_tokens,
            temperature=0.8,
            response_mime_type="application/json",
        )
        text   = response.text.strip()
        tokens = response.usage_metadata.total_token_count if hasattr(response, "usage_metadata") else len(text.split()) * 2
        return text, tokens
    except Exception as e:
        raise RuntimeError(f"Gemini error: {e}")



async def analyze_csv_mapping(headers: list, sample_row: list) -> dict:
    prompt = f"""
You are an intelligent data mapping assistant. The user has uploaded an inventory CSV.
We need to automatically identify which column contains the "Product Name" (or title), and which column contains the "Product Description".

CSV Headers: {headers}
Sample Row: {sample_row}

Return a JSON object with exactly two string keys:
"name_col": the exact header string that represents the product name.
"desc_col": the exact header string that represents the product description (or empty string if none exists).
"""
    
    provider = AI_PROVIDER
    if provider == "openai" and not OPENAI_API_KEY: provider = "gemini"
    if provider == "gemini" and not GEMINI_API_KEY: provider = "openai"

    if provider == "openai" and OPENAI_API_KEY:
        text, _ = await _generate_openai(prompt, 500)
    elif provider == "gemini" and GEMINI_API_KEY:
        text, _ = await _generate_gemini(prompt, 500)
    else:
        # Fallback to crude heuristics if no AI key is configured
        name_col = next((h for h in headers if "name" in h.lower() or "title" in h.lower()), headers[0] if headers else "")
        desc_col = next((h for h in headers if "desc" in h.lower()), "")
        return {"name_col": name_col, "desc_col": desc_col}
        
    try:
        mapping = json.loads(text)
        return mapping
    except Exception:
        # Fallback to crude heuristics if JSON parsing fails
        name_col = next((h for h in headers if "name" in h.lower() or "title" in h.lower()), headers[0] if headers else "")
        desc_col = next((h for h in headers if "desc" in h.lower()), "")
        return {"name_col": name_col, "desc_col": desc_col}

#  Main generation function 

async def generate_copy(
    copy_type:  str,
    context:    str,
    tone:       str,
    variations: int,
    max_tokens: int,
    user_id:    str,
    db:         Session,
) -> dict:
    """
    Core generation pipeline. Returns a dict with:
    - variations: list of copy strings
    - tokens_used: int
    - cost_usd: float
    - generation_time_ms: int
    """
    start_ms = time.time()

    # Build prompt
    template = PROMPTS.get(copy_type, "{context}")
    prompt   = template.format(context=context, tone=tone, variations=variations)

    # Choose provider
    provider = AI_PROVIDER
    
    if provider == "openai" and OPENAI_API_KEY:
        text, tokens = await _generate_openai(prompt, max_tokens)
    elif provider == "gemini" and GEMINI_API_KEY:
        text, tokens = await _generate_gemini(prompt, max_tokens)
    elif OPENAI_API_KEY:   # auto-fallback
        text, tokens = await _generate_openai(prompt, max_tokens)
    elif GEMINI_API_KEY:
        text, tokens = await _generate_gemini(prompt, max_tokens)
    else:
        raise RuntimeError("No AI API key configured. Set OPENAI_API_KEY or GEMINI_API_KEY in .env")

    # Parse JSON
    try:
        clean_text = text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
        
        parsed = json.loads(clean_text)
        result_variations = parsed.get("variations", [])
        if not result_variations:
            result_variations = [text]
    except Exception:
        # Fallback if json fails
        import re
        parts = [p.strip() for p in text.split("---") if p.strip()]
        if len(parts) < 2:
            parts = [re.sub(r"^\d+\.\s*", "", p).strip() for p in text.splitlines() if p.strip()]
        result_variations = parts[:variations] if parts else [text]

    result_variations = result_variations[:variations]

    generations_count = max(1, len(result_variations))
    elapsed_ms = int((time.time() - start_ms) * 1000)
    model_name = OPENAI_MODEL if provider == "openai" else GEMINI_MODEL
    cost_usd   = (tokens / 1000) * COST_PER_1K.get(model_name, 0.0002)

    # Record usage
    record = UsageRecord(
        id=str(uuid.uuid4()),
        user_id=user_id,
        endpoint="generate_copy",
        prompt_type=copy_type,
        generations_used=generations_count,
        tokens_used=tokens,
        cost_usd=round(cost_usd, 6),
        latency_ms=elapsed_ms,
    )
    db.add(record)
    db.commit()

    return {
        "variations":         result_variations,
        "generations_used":   generations_count,
        "tokens_used":        tokens,
        "cost_usd":           cost_usd,
        "generation_time_ms": elapsed_ms,
    }


async def mine_competitor_reviews(product_name: str, competitor_name: str, reviews_text: str) -> dict:
    """
    Ingests negative reviews of competitor products, extracts the top flaws,
    and produces counter-positioned product descriptions, comparison tables, and ad hooks.
    """
    product_name = _strip_emojis(product_name)
    competitor_name = _strip_emojis(competitor_name)
    reviews_text = _strip_emojis(reviews_text)

    prompt = f"""You are an expert direct-response copywriter and product strategist.
Our Product: {product_name}
Competitor Brand/Product: {competitor_name}

Here are real negative 1-star and 2-star reviews from customers who bought the competitor's product:
---
{reviews_text}
---

Your task is to analyze these reviews and generate a complete competitive counter-strategy.
Output a STRICT JSON object with no markdown wrappers (do not use ```json).
Exact required JSON structure:
{{
  "extracted_flaws": [
    "Flaw 1: specific complaint from reviews",
    "Flaw 2: specific complaint from reviews",
    "Flaw 3: specific complaint from reviews"
  ],
  "counter_description": "A compelling, benefit-rich product description (100-150 words) for {product_name} that explicitly neutralizes these flaws and reassures buyers.",
  "comparison_points": [
    {{"aspect": "Feature or build quality", "competitor_flaw": "What breaks on competitor", "our_advantage": "How our product solves it"}},
    {{"aspect": "Durability / Longevity", "competitor_flaw": "What customers complained about", "our_advantage": "Our superior construction"}},
    {{"aspect": "Customer Experience", "competitor_flaw": "Frustration point", "our_advantage": "Our guarantee / design"}}
  ],
  "ad_hooks": [
    "Hook 1: Call out the exact competitor frustration directly",
    "Hook 2: Us vs. Them contrast hook",
    "Hook 3: Problem-awareness question hook"
  ]
}}
"""
    
    provider = AI_PROVIDER
    if provider == "openai" and not OPENAI_API_KEY: provider = "gemini"
    if provider == "gemini" and not GEMINI_API_KEY: provider = "openai"

    text = ""
    try:
        if provider == "openai" and OPENAI_API_KEY:
            text, _ = await _generate_openai(prompt, 1800)
        elif provider == "gemini" and GEMINI_API_KEY:
            text, _ = await _generate_gemini(prompt, 1800)
    except Exception as e:
        logger.warning("AI competitor review mining failed: %s", e)

    data = _extract_json_block(text)
    if not data:
        data = {
            "extracted_flaws": ["Durability and customer support concerns identified in competitor reviews."],
            "counter_description": f"Engineered for maximum reliability and premium build quality, {product_name} directly addresses common industry flaws with guaranteed performance.",
            "comparison_points": [{"aspect": "Durability", "competitor_flaw": "Reported customer concerns", "our_advantage": "Precision craftsmanship"}],
            "ad_hooks": [f"Tired of fragile products? Discover the {product_name} difference."]
        }
    if "counter_description" in data:
        _, _, data["counter_description"] = audit_generated_content(data["counter_description"])
        # Keep capitalization consistent with structured comparison data when
        # an upstream model returns the same technical term in lowercase in
        # the prose.  This avoids needlessly changing the model's wording
        # while keeping the generated assets internally consistent.
        for point in data.get("comparison_points", []):
            if not isinstance(point, dict):
                continue
            for value in point.values():
                for term in re.findall(r"\b[A-Z][a-z]{2,}\b", str(value)):
                    data["counter_description"] = re.sub(
                        rf"\b{re.escape(term.lower())}\b",
                        term,
                        data["counter_description"],
                    )
    return data


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
    product_name = _strip_emojis(product_name)
    raw_details = _strip_emojis(raw_details)
    if keywords:
        keywords = _strip_emojis(keywords)
    if target_audience:
        target_audience = _strip_emojis(target_audience)

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
        # Test and local development environments commonly use placeholder
        # credentials.  Do not make an external network call for those runs;
        # the deterministic fallback below keeps the endpoint usable offline
        # and prevents a request from hanging while an SDK retries a fake key.
        use_remote_ai = os.getenv("ENVIRONMENT", "").lower() not in {"test", "testing"}
        if api_key and use_remote_ai:
            from .gemini_client import generate_content_async

            res = await generate_content_async(
                api_key=api_key,
                model=os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
                contents=prompt,
            )
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
            "backend_search_terms": f"{product_name.lower()} premium durable best high quality".encode("utf-8")[:248].decode("utf-8", "ignore"),
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
