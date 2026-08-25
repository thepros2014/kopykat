"""bounty_hunter.py — Automagic Pro bounty hunter, adapted to use KopyKat's AI engine.

Original: process_with_ai.py (used local Ollama + GitHub Actions)
This version: uses KopyKat's existing OpenAI/Gemini AI client, runs on
APScheduler instead of GitHub Actions cron, and posts Telegram notifications
via the same token already used in config.

Environment variables (add to .env):
  OPENAI_API_KEY       — OpenAI ensemble engine key
  GEMINI_API_KEY       — Gemini ensemble engine key
  GEMINI_MODEL         — Gemini model name (default: gemini-flash-latest)
  OLLAMA_HOST          — optional Ollama endpoint (default: http://localhost:11434)
  OLLAMA_MODEL         — optional local model name (default: llama3.1)
  SUPERTEAM_API_KEY      — Superteam Earn agent API key
  TELEGRAM_BOT_TOKEN     — Telegram bot token for push notifications
  TELEGRAM_CHAT_ID       — Telegram chat ID to send notifications to
  BOUNTY_MIN_FIT_SCORE   — Minimum fit score (1-10) to auto-submit (default: 7)
  BOUNTY_PORTFOLIO_LINK  — URL attached to all submitted proposals
  BOUNTY_AUTO_SUBMIT     — Set to "true" to enable autonomous submission (default: false)
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

SUPERTEAM_API_KEY: str = os.getenv("SUPERTEAM_API_KEY", "")
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
MIN_FIT_SCORE: int = int(os.getenv("BOUNTY_MIN_FIT_SCORE", "7"))
PORTFOLIO_LINK: str = os.getenv("BOUNTY_PORTFOLIO_LINK", "https://kopykat.io")
AUTO_SUBMIT: bool = os.getenv("BOUNTY_AUTO_SUBMIT", "false").lower() in {"1", "true", "yes"}

SUPERTEAM_BASE = "https://superteam.fun/api/agents"

_SCORE_RE = re.compile(r"\[SCORE:\s*(\d+)/10\]", re.IGNORECASE)
_PROPOSAL_RE = re.compile(r"<PROPOSAL>(.*?)</PROPOSAL>", re.IGNORECASE | re.DOTALL)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def send_telegram(message: str, buttons: list[dict] | None = None) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    payload: dict[str, Any] = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": [buttons]}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        logger.debug("Telegram notification failed: %s", exc)


# ---------------------------------------------------------------------------
# Superteam API helpers
# ---------------------------------------------------------------------------

def _superteam_get(path: str) -> Any:
    if not SUPERTEAM_API_KEY:
        return None
    url = f"{SUPERTEAM_BASE}/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {SUPERTEAM_API_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        logger.warning("Superteam API error for %s: %s", path, exc)
        return None


def _superteam_post(path: str, body: dict) -> Any:
    if not SUPERTEAM_API_KEY:
        return None
    url = f"{SUPERTEAM_BASE}/{path.lstrip('/')}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {SUPERTEAM_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        logger.warning("Superteam POST error for %s: %s", path, exc)
        return None


def _clean_html(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", raw or "")


def fetch_open_bounties() -> list[dict]:
    data = _superteam_get("listings/live?take=50")
    if not isinstance(data, list):
        return []
    return [
        item for item in data
        if not item.get("isWinnersAnnounced", True) and item.get("status") == "OPEN"
    ]


def fetch_bounty_details(slug: str) -> dict | None:
    return _superteam_get(f"listings/details/{slug}")


def submit_bounty(listing_id: str, proposal_text: str) -> bool:
    """Submit a proposal using the exact payload format from submit_bounty.py."""
    payload = {
        "listingId": listing_id,
        "link": PORTFOLIO_LINK,
        "tweet": "",
        "otherInfo": proposal_text,
        "eligibilityAnswers": [],
        "ask": None,
        "telegram": None,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://superteam.fun/api/agents/submissions/create",
        data=data,
        headers={
            "Authorization": f"Bearer {SUPERTEAM_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())
            logger.info("Submission response: %s", result)
            return True
    except Exception as exc:
        logger.warning("Submission failed for listing %s: %s", listing_id, exc)
        return False




# ---------------------------------------------------------------------------
# AI evaluation — 3-engine ensemble (OpenAI + Gemini + Ollama)
# ---------------------------------------------------------------------------

async def _evaluate_bounty_ensemble(title: str, description: str) -> dict:
    """Run the 3-engine ensemble evaluator. Returns the full ensemble result dict."""
    try:
        from .multi_ai_evaluator import evaluate_bounty
        return await evaluate_bounty(title, description)
    except Exception as exc:
        logger.error("Ensemble evaluation failed for '%s': %s", title, exc)
        return {
            "ensemble_score": 0,
            "engines_responded": 0,
            "majority_recommends": False,
            "best_proposal": None,
            "breakdown": [],
        }


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

async def run_bounty_hunter() -> dict[str, Any]:
    """
    Fetch open bounties, evaluate each with the 3-engine AI ensemble,
    and optionally auto-submit based on majority recommendation.
    Returns a summary dict with counts and results.
    """
    if not SUPERTEAM_API_KEY:
        logger.info("SUPERTEAM_API_KEY not set — bounty hunter skipped.")
        return {"status": "skipped", "reason": "SUPERTEAM_API_KEY not configured"}

    logger.info("[%s] Bounty hunter (3-engine ensemble) starting...", datetime.utcnow().isoformat())
    bounties = fetch_open_bounties()
    if not bounties:
        logger.info("No open bounties found.")
        return {"status": "ok", "evaluated": 0, "submitted": 0}

    logger.info("Found %d open bounties. Running 3-engine ensemble evaluation...", len(bounties))
    evaluated = 0
    submitted = 0
    results = []

    for item in bounties:
        slug = item.get("slug", "")
        listing_id = item.get("id", "")
        title = item.get("title", "Unknown")
        reward = f"{item.get('rewardAmount', '?')} {item.get('token', '')}"

        details = fetch_bounty_details(slug)
        if not details:
            continue

        description = _clean_html(details.get("description", ""))
        ensemble = await _evaluate_bounty_ensemble(title, description)
        evaluated += 1

        ensemble_score = ensemble.get("ensemble_score", 0)
        majority_recommends = ensemble.get("majority_recommends", False)
        best_proposal = ensemble.get("best_proposal")
        engines_responded = ensemble.get("engines_responded", 0)
        breakdown = ensemble.get("breakdown", [])

        # Build score summary string for logging and Telegram
        score_parts = [
            f"{e.get('engine', 'unknown')}={e.get('score')}/10"
            for e in breakdown if e.get("score") is not None
        ]
        score_summary = " | ".join(score_parts) if score_parts else "no scores"

        result_entry: dict[str, Any] = {
            "title": title,
            "reward": reward,
            "slug": slug,
            "ensemble_score": ensemble_score,
            "engines_responded": engines_responded,
            "score_breakdown": score_summary,
            "majority_recommends": majority_recommends,
            "submitted": False,
        }

        if majority_recommends and best_proposal:
            if AUTO_SUBMIT:
                ok = submit_bounty(listing_id, best_proposal)
                if ok:
                    submitted += 1
                    result_entry["submitted"] = True
                    logger.info(
                        "Auto-submitted '%s' — ensemble %.1f/10 (%s)",
                        title, ensemble_score, score_summary,
                    )
                    send_telegram(
                        f"<b>AUTO-SUBMITTED — 3-ENGINE CONSENSUS</b>\n\n"
                        f"<b>Title:</b> {title}\n"
                        f"<b>Reward:</b> {reward}\n"
                        f"<b>Ensemble Score:</b> {ensemble_score}/10\n"
                        f"<b>Engines:</b> {score_summary}",
                        buttons=[{"text": "View Bounty", "url": f"https://superteam.fun/bounties/{slug}"}],
                    )
            else:
                logger.info(
                    "Bounty '%s' — ensemble %.1f/10 (%s) — majority recommends, "
                    "but BOUNTY_AUTO_SUBMIT is OFF.",
                    title, ensemble_score, score_summary,
                )
                send_telegram(
                    f"<b>BOUNTY READY TO SUBMIT</b>\n\n"
                    f"<b>Title:</b> {title}\n"
                    f"<b>Reward:</b> {reward}\n"
                    f"<b>Ensemble Score:</b> {ensemble_score}/10\n"
                    f"<b>Engines:</b> {score_summary}\n\n"
                    f"Auto-submit is OFF. Trigger manually via admin endpoint.",
                    buttons=[{"text": "View Bounty", "url": f"https://superteam.fun/bounties/{slug}"}],
                )
        else:
            logger.debug(
                "Bounty '%s' — ensemble %.1f/10 (%s) — majority does NOT recommend.",
                title, ensemble_score, score_summary,
            )

        results.append(result_entry)

    summary = {
        "status": "ok",
        "ranAt": datetime.utcnow().isoformat() + "Z",
        "evaluated": evaluated,
        "submitted": submitted,
        "autoSubmitEnabled": AUTO_SUBMIT,
        "minFitScore": MIN_FIT_SCORE,
        "engines": ["openai", "gemini", "ollama"],
        "results": results,
    }
    logger.info(
        "3-engine bounty hunter complete — evaluated: %d | submitted: %d",
        evaluated, submitted,
    )
    return summary


def run_bounty_hunter_sync() -> None:
    """Synchronous APScheduler entry point."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(run_bounty_hunter())
        else:
            loop.run_until_complete(run_bounty_hunter())
    except Exception:
        logger.exception("Bounty hunter scheduler run failed")
