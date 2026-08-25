"""multi_ai_evaluator.py — 3-engine ensemble for bounty evaluation.

Runs all three AI providers concurrently against each bounty:
  1. OpenAI  (gpt-4o-mini via openai SDK)
  2. Gemini  (gemini-flash-latest via google-genai SDK)
  3. Local   (llama3.1 via Ollama at localhost:11434)

Each engine returns:
  - A fit score [SCORE: X/10]
  - A proposal inside <PROPOSAL>...</PROPOSAL> tags

Ensemble logic:
  - Score = average of all engines that responded (minimum 1)
  - Proposal = taken from the highest-scoring engine
  - If 2/3 engines score >= threshold → submission recommended
  - Full per-engine breakdown is logged and stored for transparency

Environment variables:
  OPENAI_API_KEY    — enables OpenAI engine
  GEMINI_API_KEY    — enables Gemini engine
  OLLAMA_HOST       — Ollama base URL (default: http://localhost:11434)
  OLLAMA_MODEL      — model name (default: llama3.1)
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1")

_SCORE_RE = re.compile(r"\[SCORE:\s*(\d+)/10\]", re.IGNORECASE)
_PROPOSAL_RE = re.compile(r"<PROPOSAL>(.*?)</PROPOSAL>", re.IGNORECASE | re.DOTALL)

SYSTEM_PROMPT = (
    "You are a world-class software architect and business strategist. "
    "Evaluate the following bounty opportunity precisely and honestly. "
    "Output EXACTLY in this order:\n"
    "1. [SCORE: X/10] — your fit score (X is an integer 1-10)\n"
    "2. <PROPOSAL>your 2-paragraph proposal here</PROPOSAL>\n"
    "Be specific, professional, and concise."
)


# ---------------------------------------------------------------------------
# Per-engine callers
# ---------------------------------------------------------------------------

async def _call_openai(prompt: str) -> dict[str, Any]:
    """Call OpenAI API asynchronously."""
    if not OPENAI_API_KEY:
        return {"engine": "openai", "available": False, "score": None, "proposal": None, "raw": ""}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENAI_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 600,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"].strip()
            return _parse_response("openai", raw)
    except Exception as exc:
        logger.warning("OpenAI engine error: %s", exc)
        return {"engine": "openai", "available": True, "error": str(exc), "score": None, "proposal": None, "raw": ""}


async def _call_gemini(prompt: str) -> dict[str, Any]:
    """Call Gemini API asynchronously using the existing gemini_client."""
    if not GEMINI_API_KEY:
        return {"engine": "gemini", "available": False, "score": None, "proposal": None, "raw": ""}
    try:
        from ..gemini_client import generate_content_async
        result = await generate_content_async(
            api_key=GEMINI_API_KEY,
            model=GEMINI_MODEL,
            contents=prompt,
            system_instruction=SYSTEM_PROMPT,
            temperature=0.3,
            max_output_tokens=600,
        )
        raw = result.text.strip() if hasattr(result, "text") else str(result)
        return _parse_response("gemini", raw)
    except Exception as exc:
        logger.warning("Gemini engine error: %s", exc)
        return {"engine": "gemini", "available": True, "error": str(exc), "score": None, "proposal": None, "raw": ""}


async def _call_ollama(prompt: str) -> dict[str, Any]:
    """Call local Ollama instance asynchronously."""
    try:
        async with httpx.AsyncClient() as client:
            # First check Ollama is up
            health = await client.get(OLLAMA_HOST, timeout=3.0)
            health.raise_for_status()

            resp = await client.post(
                f"{OLLAMA_HOST}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": f"{SYSTEM_PROMPT}\n\n{prompt}",
                    "stream": False,
                    "options": {"temperature": 0.3},
                },
                timeout=120.0,  # Local LLM can be slow
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()
            return _parse_response("ollama", raw)
    except httpx.ConnectError:
        logger.info("Ollama not running at %s — local engine skipped.", OLLAMA_HOST)
        return {"engine": "ollama", "available": False, "score": None, "proposal": None, "raw": ""}
    except Exception as exc:
        logger.warning("Ollama engine error: %s", exc)
        return {"engine": "ollama", "available": True, "error": str(exc), "score": None, "proposal": None, "raw": ""}


def _parse_response(engine: str, raw: str) -> dict[str, Any]:
    """Extract score and proposal from a raw AI response."""
    score_match = _SCORE_RE.search(raw)
    proposal_match = _PROPOSAL_RE.search(raw)
    score = int(score_match.group(1)) if score_match else None
    if score is not None and not 1 <= score <= 10:
        score = None
    return {
        "engine": engine,
        "available": True,
        "score": score,
        "proposal": proposal_match.group(1).strip() if proposal_match else None,
        "raw": raw[:800],  # Keep truncated copy for logging
    }


# ---------------------------------------------------------------------------
# Ensemble aggregator
# ---------------------------------------------------------------------------

async def evaluate_bounty(title: str, description: str) -> dict[str, Any]:
    """
    Run all 3 AI engines concurrently and blend their results.

    Returns:
        {
            "ensemble_score": float,       # average of responding engines
            "engines_responded": int,      # how many engines returned a score
            "majority_recommends": bool,   # True if 2/3 engines scored >= threshold
            "best_proposal": str | None,   # proposal from highest-scoring engine
            "breakdown": [...]             # per-engine detail
        }
    """
    prompt = (
        f"Bounty Title: {title}\n\n"
        f"Description:\n{description[:3500]}"
    )

    # Run all 3 engines in parallel
    openai_result, gemini_result, ollama_result = await asyncio.gather(
        _call_openai(prompt),
        _call_gemini(prompt),
        _call_ollama(prompt),
        return_exceptions=False,
    )

    breakdown = [openai_result, gemini_result, ollama_result]

    # Filter to engines that responded with a numeric score
    scored = [e for e in breakdown if e.get("score") is not None]
    engines_responded = len(scored)

    if not scored:
        logger.warning("No AI engines returned a valid score for bounty: %s", title)
        return {
            "ensemble_score": 0,
            "engines_responded": 0,
            "majority_recommends": False,
            "best_proposal": None,
            "breakdown": breakdown,
        }

    # Ensemble score = simple average
    ensemble_score = round(sum(e["score"] for e in scored) / engines_responded, 1)

    # Best proposal = from highest-scoring engine that has one
    proposals_with_score = [
        e for e in scored if e.get("proposal")
    ]
    best_proposal: str | None = None
    if proposals_with_score:
        best_engine = max(proposals_with_score, key=lambda e: e["score"])
        best_proposal = best_engine["proposal"]

    # Majority vote: at least 2 of however many responded scored >= 7
    threshold = int(os.getenv("BOUNTY_MIN_FIT_SCORE", "7"))
    votes_for = sum(1 for e in scored if e["score"] >= threshold)
    majority_recommends = votes_for >= max(2, len(scored) // 2 + 1)

    logger.info(
        "Ensemble eval for '%s' — scores: %s → avg %.1f | majority: %s",
        title,
        [f"{e['engine']}={e['score']}" for e in scored],
        ensemble_score,
        majority_recommends,
    )

    return {
        "ensemble_score": ensemble_score,
        "engines_responded": engines_responded,
        "majority_recommends": majority_recommends,
        "best_proposal": best_proposal,
        "breakdown": breakdown,
    }
