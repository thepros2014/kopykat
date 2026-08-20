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
        "Start with a strong hook, provide value or a bold claim, use appropriate emojis, and end with a CTA.\n\n"
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
    "You are SnapCopy AI, an elite, world-class direct-response copywriter. "
    "You write high-converting copy that drives sales. "
    "CRITICAL INSTRUCTION: You MUST output your response strictly as a JSON object with a single key 'variations' which is an array of strings. "
    "Do NOT wrap the JSON in markdown code blocks. Do NOT output any conversational text. "
    "Example format: {\"variations\": [\"variation 1 text\", \"variation 2 text\"]}"
)


#  OpenAI generation 

async def _generate_openai(prompt: str, max_tokens: int) -> tuple[str, int]:
    """Returns (text, tokens_used)."""
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.8,
            response_format={ "type": "json_object" }
        )
        text   = response.choices[0].message.content.strip()
        tokens = response.usage.total_tokens
        return text, tokens
    except Exception as e:
        raise RuntimeError(f"OpenAI error: {e}")


#  Gemini generation 

async def _generate_gemini(prompt: str, max_tokens: int) -> tuple[str, int]:
    """Returns (text, tokens_used). Gemini token counts are estimated."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model    = genai.GenerativeModel(GEMINI_MODEL, system_instruction=SYSTEM_PROMPT)
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=max_tokens,
                temperature=0.8,
                response_mime_type="application/json"
            ),
        )
        text   = response.text.strip()
        tokens = response.usage_metadata.total_token_count if hasattr(response, "usage_metadata") else len(text.split()) * 2
        return text, tokens
    except Exception as e:
        raise RuntimeError(f"Gemini error: {e}")


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
