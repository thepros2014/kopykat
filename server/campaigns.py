import json
import os
import logging
import random
import re

from .gemini_client import generate_content, image_part
from .ai_credentials import get_active_ai_credentials

logger = logging.getLogger(__name__)


def _generate_campaign_text(prompt: str, *, gemini_model: str) -> str:
    """Generate campaign JSON using the request-scoped provider when present."""

    customer_credentials = get_active_ai_credentials()
    if customer_credentials and customer_credentials.provider == "openai":
        from .openai_client import generate_text

        text, _ = generate_text(
            api_key=customer_credentials.api_key,
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            input_value=prompt,
            max_output_tokens=2500,
            temperature=0.8,
            json_mode=True,
        )
        return text

    api_key = customer_credentials.api_key if customer_credentials else os.environ.get("GEMINI_API_KEY", "")
    response = generate_content(
        api_key=api_key,
        model=gemini_model,
        contents=prompt,
    )
    return response.text

def scrape_pain_points(keyword: str) -> str:
    """
    Simulates a social listening tool (like scraping Reddit/Twitter).
    In a real production environment, this would call Serper/Reddit API.
    """
    logger.info(f"Scraping social pain points for: {keyword}")
    
    # Mocked social signals for the MVP
    pain_points = [
        "Users are frustrated by how complicated existing tools are. They want '1-click' solutions.",
        f"People complain that {keyword} is too expensive for small businesses.",
        "A common thread on Reddit mentions terrible customer support in this industry.",
        "Users hate paying for features they don't use. They want modular pricing.",
        "There's a massive gap in automation; users are manually transferring data between platforms."
    ]
    
    selected = random.sample(pain_points, 3)
    return " | ".join(selected)

def generate_omni_campaign(keyword: str, product_desc: str) -> dict:
    """
    Generates a full cohesive campaign (Blog, Emails, Social) based on market pain points.
    """
    pain_points = scrape_pain_points(keyword)
    
    prompt = f"""You are an elite direct-response marketer and copywriter.
    
We are selling the following product/service: {product_desc}
Target Keyword/Market: {keyword}

I just scraped social media (Reddit/Twitter) for what this market is currently complaining about. 
Here are their active pain points: {pain_points}

Your job is to generate a cohesive Omni-Channel Marketing Campaign that directly addresses these pain points.
Format your output as a STRICT JSON object with no markdown wrappers (do not use ```json).
The JSON must have the following exact structure:

{{
  "blog_post": {{
    "title": "A catchy, SEO-optimized title",
    "content": "The full blog post in HTML format (using <h2>, <h3>, <p>, <ul>). It should address the pain points."
  }},
  "email_drip": [
    {{
      "subject": "Subject for Email 1 (Problem Awareness)",
      "body": "HTML body for email 1 using PAS framework."
    }},
    {{
      "subject": "Subject for Email 2 (Agitation & Solution)",
      "body": "HTML body for email 2."
    }},
    {{
      "subject": "Subject for Email 3 (Urgency/Offer)",
      "body": "HTML body for email 3."
    }}
  ],
  "social_posts": [
    "Engaging Twitter/LinkedIn style post 1",
    "Engaging Twitter/LinkedIn style post 2",
    "Engaging Twitter/LinkedIn style post 3"
  ]
}}
"""
    
    text = _generate_campaign_text(
        prompt,
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"),
    ).strip()
    
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
        
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        logger.error(f"Failed to parse Omni-Campaign JSON: {text}")
        raise ValueError("AI returned invalid campaign formatting. Please try again.")


def generate_demo_campaign(keyword: str, product_desc: str) -> dict:
    pain_points = scrape_pain_points(keyword)
    
    prompt = f"""You are an elite marketer.
Product: {product_desc}
Keyword: {keyword}
Pain Points: {pain_points}

Generate a SHORT TEASER marketing campaign in strict JSON format. 
DO NOT include markdown wrappers like ```json.
{{
  "blog_post": {{
    "title": "A catchy, SEO-optimized title",
    "content": "<p>A short introductory paragraph teasing the blog post.</p>"
  }},
  "email_drip": [
    {{
      "subject": "Teaser Email Subject",
      "body": "<p>A short teaser email body.</p>"
    }}
  ],
  "social_posts": [
    "A short teaser social post."
  ]
}}
"""
    
    text = _generate_campaign_text(
        prompt,
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"),
    ).strip()
    
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
        
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        logger.error(f"Failed to parse Demo Omni-Campaign JSON: {text}")
        raise ValueError("AI returned invalid formatting. Please try again.")


def _extract_clean_json(text: str) -> dict:
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
        raise ValueError("AI returned invalid campaign formatting. Please try again.")


def _generate_fallback_vision_campaign(keyword: str = "", extra_context: str = "") -> dict:
    """
    Deterministic offline fallback for vision-based omni-channel campaigns.
    """
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


def generate_omni_campaign_from_image(image_bytes: bytes, mime_type: str = "image/jpeg", keyword: str = "", extra_context: str = "", allow_fallback: bool = False) -> dict:
    """
    Uses Vision AI (Gemini / GPT-4o) to analyze product images and generate a full,
    multi-channel marketing campaign and product descriptions.
    """
    pain_points = scrape_pain_points(keyword or "e-commerce product")
    
    prompt = f"""You are an elite direct-response marketer, product catalog specialist, and copywriter.
Analyze the provided product image in detail. Identify the product type, key visual features, materials/design, target audience, and emotional appeal.
Additional user context: {extra_context or 'None provided'}
Target Keyword / Category: {keyword or 'Identified from image'}

Market complaints/pain points: {pain_points}

Generate a comprehensive, cohesive Omni-Channel Marketing Campaign.
Format output as a STRICT JSON object with no markdown wrappers (do not use ```json).
Exact structure required:
{{
  "detected_product_name": "Accurate, marketable product title (5-10 words)",
  "detected_description": "Detailed, benefit-rich product description (100-150 words)",
  "blog_post": {{
    "title": "A catchy, SEO-optimized title",
    "content": "Full blog post in clean HTML format with <h2>, <h3>, <p>, <ul>."
  }},
  "email_drip": [
    {{
      "subject": "Email 1 Subject (Hook & Problem Awareness)",
      "body": "HTML body for email 1 using PAS framework."
    }},
    {{
      "subject": "Email 2 Subject (Social Proof & Benefits)",
      "body": "HTML body for email 2."
    }},
    {{
      "subject": "Email 3 Subject (Urgency & Direct Call to Action)",
      "body": "HTML body for email 3."
    }}
  ],
  "social_posts": [
    "Engaging Instagram/Facebook product post with hashtags",
    "Punchy Twitter/X post highlighting key transformation",
    "Professional LinkedIn/Pinterest product highlight"
  ]
}}
"""
    
    customer_credentials = get_active_ai_credentials()
    if customer_credentials:
        if customer_credentials.provider == "gemini":
            try:
                response = generate_content(
                    api_key=customer_credentials.api_key,
                    model=os.environ.get('GEMINI_MODEL', 'gemini-1.5-flash'),
                    contents=[image_part(image_bytes, mime_type or "image/jpeg"), prompt],
                )
                return _extract_clean_json(response.text)
            except Exception as e:
                logger.warning("Customer Gemini vision failed: %s", e)
        else:
            try:
                from .openai_client import generate_vision_json

                text, _ = generate_vision_json(
                    api_key=customer_credentials.api_key,
                    model=os.environ.get('OPENAI_MODEL', 'gpt-4o-mini'),
                    image_bytes=image_bytes,
                    mime_type=mime_type or 'image/jpeg',
                    prompt=prompt,
                    max_output_tokens=2500,
                )
                return _extract_clean_json(text)
            except Exception as e:
                logger.warning("Customer OpenAI vision failed: %s", e)
        if allow_fallback:
            return _generate_fallback_vision_campaign(keyword, extra_context)
        raise ValueError("Vision campaign generation failed with the configured BYOK provider.")

    gemini_key = os.environ.get('GEMINI_API_KEY', '')
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    provider = os.environ.get('AI_PROVIDER', 'openai').lower()
    
    # 1. Try Gemini Vision if preferred or available
    if (provider == 'gemini' and gemini_key) or (gemini_key and not openai_key):
        try:
            model_name = os.environ.get('GEMINI_MODEL', 'gemini-1.5-flash')
            response = generate_content(
                api_key=gemini_key,
                model=model_name,
                contents=[image_part(image_bytes, mime_type or "image/jpeg"), prompt],
            )
            return _extract_clean_json(response.text)
        except Exception as e:
            logger.warning(f"Gemini vision failed: {e}. Attempting fallback...")
            if not openai_key:
                if allow_fallback:
                    return _generate_fallback_vision_campaign(keyword, extra_context)
                raise ValueError(f"Vision campaign generation failed: {e}")
    
    # 2. Try OpenAI Vision (GPT-4o / GPT-4o-mini)
    if openai_key:
        try:
            from .openai_client import generate_vision_json

            text, _ = generate_vision_json(
                api_key=openai_key,
                model=os.environ.get('OPENAI_MODEL', 'gpt-4o-mini'),
                image_bytes=image_bytes,
                mime_type=mime_type or 'image/jpeg',
                prompt=prompt,
                max_output_tokens=2500,
            )
            return _extract_clean_json(text)
        except Exception as e:
            logger.error(f"OpenAI vision failed: {e}")
            if allow_fallback:
                return _generate_fallback_vision_campaign(keyword, extra_context)
            raise ValueError(f"Vision campaign generation failed: {e}")
            
    if allow_fallback:
        return _generate_fallback_vision_campaign(keyword, extra_context)
    raise ValueError("No AI API key configured. Set GEMINI_API_KEY or OPENAI_API_KEY in .env")
