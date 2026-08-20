"""
ai_engine.py — AI content generation.
Supports OpenAI GPT-4o and Google Gemini. Falls back automatically.
"""

import os
import time
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from .database import UsageRecord

# ── Config ────────────────────────────────────────────────────────────────────

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

# ── Prompt templates for each copy type ──────────────────────────────────────

PROMPTS = {
    "product_description": (
        "Write a compelling product description for the following. "
        "Focus on benefits, not features. Use sensory language. Keep it under 150 words.\n\n"
        "Product/Context: {context}\n\nTone: {tone}"
    ),
    "email_subject": (
        "Write {variations} email subject line(s) that maximize open rates. "
        "Use curiosity, urgency, or personalization. Each on a new line.\n\n"
        "Context: {context}\n\nTone: {tone}"
    ),
    "email_body": (
        "Write a persuasive marketing email body. Include a clear CTA. "
        "Keep it concise and scannable with short paragraphs.\n\n"
        "Context: {context}\n\nTone: {tone}"
    ),
    "social_post": (
        "Write {variations} social media post(s) with strong hooks. "
        "Include relevant emojis and a call to action. Each separated by ---.\n\n"
        "Context: {context}\n\nTone: {tone}"
    ),
    "ad_headline": (
        "Write {variations} high-converting ad headline(s), max 10 words each. "
        "Make each one punch hard and create curiosity or desire.\n\n"
        "Context: {context}\n\nTone: {tone}"
    ),
    "ad_body": (
        "Write persuasive ad copy body text that supports a headline. "
        "Highlight the key benefit, address an objection, and end with a CTA.\n\n"
        "Context: {context}\n\nTone: {tone}"
    ),
    "landing_page_hero": (
        "Write a landing page hero section: headline, subheadline, and CTA button text. "
        "Format as:\nHeadline: ...\nSubheadline: ...\nCTA: ...\n\n"
        "Context: {context}\n\nTone: {tone}"
    ),
    "call_to_action": (
        "Write {variations} powerful call-to-action button texts (3-8 words each). "
        "Make them action-oriented and benefit-driven. Each on a new line.\n\n"
        "Context: {context}\n\nTone: {tone}"
    ),
    "seo_meta_description": (
        "Write an SEO meta description under 160 characters. Include the primary keyword naturally. "
        "Make it compelling enough to earn the click.\n\n"
        "Context: {context}"
    ),
    "blog_intro": (
        "Write a captivating blog post introduction (150-200 words) that hooks the reader "
        "immediately, establishes the problem, and previews the solution.\n\n"
        "Topic/Context: {context}\n\nTone: {tone}"
    ),
}

SYSTEM_PROMPT = (
    "You are SnapCopy AI, a world-class marketing copywriter. "
    "You write high-converting, professional copy that drives results. "
    "Be direct, specific, and persuasive. Never use filler phrases like 'Certainly!' or 'Of course!'. "
    "Output ONLY the requested copy — no explanations, no meta-commentary."
)


# ── OpenAI generation ─────────────────────────────────────────────────────────

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
        )
        text   = response.choices[0].message.content.strip()
        tokens = response.usage.total_tokens
        return text, tokens
    except Exception as e:
        raise RuntimeError(f"OpenAI error: {e}")


# ── Gemini generation ─────────────────────────────────────────────────────────

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
            ),
        )
        text   = response.text.strip()
        # Gemini doesn't always expose token counts in free tier — estimate
        tokens = response.usage_metadata.total_token_count if hasattr(response, "usage_metadata") else len(text.split()) * 2
        return text, tokens
    except Exception as e:
        raise RuntimeError(f"Gemini error: {e}")


# ── Main generation function ──────────────────────────────────────────────────

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

    # Split into individual variations if multiple requested
    if variations > 1:
        parts = [p.strip() for p in text.split("---") if p.strip()]
        # Also split by numbered list if --- not present
        if len(parts) < 2:
            import re
            parts = [re.sub(r"^\d+\.\s*", "", p).strip() for p in text.splitlines() if p.strip()]
        result_variations = parts[:variations] if parts else [text]
    else:
        result_variations = [text]

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
