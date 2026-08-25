"""bounty_hunter.py — Automagic Pro bounty hunter, adapted to use KopyKat's AI engine.

Original: process_with_ai.py (used local Ollama + GitHub Actions)
This version: uses KopyKat's existing OpenAI/Gemini AI client, runs on
APScheduler instead of GitHub Actions cron, and posts Telegram notifications
via the same token already used in config.

Environment variables (add to .env):
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
# AI evaluation — uses KopyKat's existing AI engine
# ---------------------------------------------------------------------------

async def _evaluate_bounty_with_ai(title: str, description: str) -> str:
    """Call KopyKat's AI engine to evaluate the bounty and produce a proposal."""
    try:
        from ..ai_engine import generate_copy
        prompt = (
            "You are a world-class software and business consultant. "
            "Evaluate this bounty opportunity and produce a professional proposal.\n\n"
            f"Bounty Title: {title}\n\n"
            f"Description:\n{description[:3000]}\n\n"
            "Instructions:\n"
            "1. Rate our fit out of 10. Output EXACTLY: [SCORE: X/10]\n"
            "2. Draft a compelling 2-paragraph proposal enclosed in <PROPOSAL></PROPOSAL> tags.\n"
            "Keep the proposal professional, specific to the bounty, and under 300 words."
        )
        result = await generate_copy(
            keyword=title,
            product_desc=description[:500],
            channels=["custom"],
            platform_hint="proposal",
            extra_instructions=prompt,
        )
        return str(result)
    except Exception as exc:
        logger.error("AI evaluation failed for bounty '%s': %s", title, exc)
        return ""


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

async def run_bounty_hunter() -> dict[str, Any]:
    """
    Fetch open bounties, evaluate each with AI, and optionally auto-submit.
    Returns a summary dict with counts and results.
    """
    if not SUPERTEAM_API_KEY:
        logger.info("SUPERTEAM_API_KEY not set — bounty hunter skipped.")
        return {"status": "skipped", "reason": "SUPERTEAM_API_KEY not configured"}

    logger.info("[%s] Bounty hunter starting...", datetime.utcnow().isoformat())
    bounties = fetch_open_bounties()
    if not bounties:
        logger.info("No open bounties found.")
        return {"status": "ok", "evaluated": 0, "submitted": 0}

    logger.info("Found %d open bounties. Evaluating...", len(bounties))
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
        evaluation = await _evaluate_bounty_with_ai(title, description)
        evaluated += 1

        score_match = _SCORE_RE.search(evaluation)
        proposal_match = _PROPOSAL_RE.search(evaluation)
        score = int(score_match.group(1)) if score_match else 0

        result_entry: dict[str, Any] = {
            "title": title,
            "reward": reward,
            "slug": slug,
            "score": score,
            "submitted": False,
        }

        if score >= MIN_FIT_SCORE and proposal_match:
            proposal_text = proposal_match.group(1).strip()
            if AUTO_SUBMIT:
                ok = submit_bounty(listing_id, proposal_text)
                if ok:
                    submitted += 1
                    result_entry["submitted"] = True
                    logger.info("Auto-submitted proposal for: %s (score %d/10)", title, score)
                    send_telegram(
                        f"<b>AUTO-SUBMITTED BOUNTY</b>\n\n"
                        f"<b>Title:</b> {title}\n"
                        f"<b>Reward:</b> {reward}\n"
                        f"<b>Fit Score:</b> {score}/10",
                        buttons=[{"text": "View Bounty", "url": f"https://superteam.fun/bounties/{slug}"}],
                    )
            else:
                logger.info(
                    "Bounty '%s' scored %d/10 — auto-submit is OFF. "
                    "Set BOUNTY_AUTO_SUBMIT=true to enable autonomous submission.",
                    title, score,
                )
        else:
            logger.debug("Bounty '%s' scored %d/10 — below threshold %d.", title, score, MIN_FIT_SCORE)

        results.append(result_entry)

    summary = {
        "status": "ok",
        "ranAt": datetime.utcnow().isoformat() + "Z",
        "evaluated": evaluated,
        "submitted": submitted,
        "autoSubmitEnabled": AUTO_SUBMIT,
        "minFitScore": MIN_FIT_SCORE,
        "results": results,
    }
    logger.info(
        "Bounty hunter complete — evaluated: %d | submitted: %d | auto-submit: %s",
        evaluated, submitted, AUTO_SUBMIT,
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
