"""bounty_monitor.py — Fast 30-minute bounty scanner, ported from bounty-monitor.yml.

Polls Superteam Earn every 30 minutes for open agent bounties.
Persists monitor_status.json and tracks seen bounty IDs to prevent
double-submissions. This is the lightweight "radar" — it just watches
and records. The AI-evaluated bounty_hunter.py handles intelligent
proposal writing and submission.

Environment variables:
  SUPERTEAM_API_KEY         — required to poll the API
  BOUNTY_PORTFOLIO_LINK     — link attached to quick-submit proposals
  BOUNTY_MONITOR_SUBMIT     — set "true" to enable instant (no-AI) submission
                              for bounties that pass the open check
  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID — push notifications
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SUPERTEAM_API_KEY: str = os.getenv("SUPERTEAM_API_KEY", "")
PORTFOLIO_LINK: str = os.getenv("BOUNTY_PORTFOLIO_LINK", "https://kopykat.io")
MONITOR_SUBMIT: bool = os.getenv("BOUNTY_MONITOR_SUBMIT", "false").lower() in {"1", "true", "yes"}
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

_HERE = Path(__file__).parent
DATA_DIR = _HERE / "data"
MONITOR_STATUS_PATH = DATA_DIR / "monitor_status.json"
SEEN_BOUNTIES_PATH = DATA_DIR / "seen_bounties.json"

SUPERTEAM_LISTINGS_URL = "https://superteam.fun/api/agents/listings/live?take=50"
SUPERTEAM_SUBMIT_URL = "https://superteam.fun/api/agents/submissions/create"

SUBMIT_OTHER_INFO = (
    "SolPulse AI — Autonomous Solana Narrative Detection & Idea Generation Engine. "
    "Built with KopyKat's AI platform. "
    f"Live App: {PORTFOLIO_LINK}"
)


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path: Path, data: Any) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def get_monitor_status() -> dict | None:
    """Return latest monitor_status.json payload."""
    return _load_json(MONITOR_STATUS_PATH, None)


def _seen_bounties() -> set[str]:
    data = _load_json(SEEN_BOUNTIES_PATH, [])
    return set(data) if isinstance(data, list) else set()


def _mark_seen(bounty_ids: list[str]) -> None:
    seen = _seen_bounties()
    seen.update(bounty_ids)
    # Keep only the last 500 to prevent unbounded growth
    trimmed = list(seen)[-500:]
    _save_json(SEEN_BOUNTIES_PATH, trimmed)


# ---------------------------------------------------------------------------
# Superteam API
# ---------------------------------------------------------------------------

def _superteam_get(url: str) -> Any:
    if not SUPERTEAM_API_KEY:
        return None
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {SUPERTEAM_API_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:
        logger.warning("Superteam GET error: %s", exc)
        return None


def _superteam_submit(listing_id: str, title: str) -> bool:
    if not SUPERTEAM_API_KEY:
        return False
    payload = {
        "listingId": listing_id,
        "link": PORTFOLIO_LINK,
        "tweet": "",
        "otherInfo": SUBMIT_OTHER_INFO,
        "eligibilityAnswers": [],
        "ask": None,
        "telegram": None,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        SUPERTEAM_SUBMIT_URL,
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
            logger.info("Quick-submitted bounty '%s' → %s", title, result)
            return True
    except Exception as exc:
        logger.warning("Submission failed for '%s': %s", title, exc)
        return False


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def _notify(message: str, buttons: list | None = None) -> None:
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
# Main monitor run
# ---------------------------------------------------------------------------

def run_bounty_monitor() -> dict[str, Any]:
    """
    Poll Superteam for open bounties, persist status, optionally quick-submit.
    Safe to call from APScheduler — fully synchronous, no async needed.
    """
    if not SUPERTEAM_API_KEY:
        logger.info("SUPERTEAM_API_KEY not configured — bounty monitor skipped.")
        return {"status": "skipped", "reason": "SUPERTEAM_API_KEY not set"}

    now = datetime.now(tz=timezone.utc).isoformat()
    logger.info("[%s] Bounty monitor checking Superteam Earn...", now)

    raw = _superteam_get(SUPERTEAM_LISTINGS_URL)
    if not isinstance(raw, list):
        logger.warning("Unexpected response from Superteam listings API.")
        status = {"lastCheck": now, "openBounties": 0, "listings": [], "error": "bad_response"}
        _save_json(MONITOR_STATUS_PATH, status)
        return status

    open_listings = [
        item for item in raw
        if not item.get("isWinnersAnnounced", True) and item.get("status") == "OPEN"
    ]

    logger.info(
        "Bounty monitor — total live: %d | open (no winners): %d",
        len(raw), len(open_listings),
    )

    seen = _seen_bounties()
    new_bounties = [b for b in open_listings if b.get("id") not in seen]
    submitted_ids: list[str] = []

    compact_listings = [
        {
            "id": b.get("id"),
            "title": b.get("title"),
            "reward": f"{b.get('rewardAmount', '?')} {b.get('token', '')}",
            "slug": b.get("slug"),
            "url": f"https://superteam.fun/bounties/{b.get('slug', '')}",
        }
        for b in open_listings
    ]

    if new_bounties:
        logger.info("Found %d NEW bounty(ies) not seen before.", len(new_bounties))
        for b in new_bounties:
            b_id = b.get("id", "")
            b_title = b.get("title", "Unknown")
            b_reward = f"{b.get('rewardAmount', '?')} {b.get('token', '')}"
            b_slug = b.get("slug", "")

            if MONITOR_SUBMIT:
                ok = _superteam_submit(b_id, b_title)
                if ok:
                    submitted_ids.append(b_id)
                    _notify(
                        f"<b>BOUNTY DETECTED + SUBMITTED</b>\n\n"
                        f"<b>Title:</b> {b_title}\n"
                        f"<b>Reward:</b> {b_reward}",
                        buttons=[{"text": "View Bounty", "url": f"https://superteam.fun/bounties/{b_slug}"}],
                    )
            else:
                logger.info("  NEW → '%s' | %s (monitor-submit is OFF)", b_title, b_reward)
                _notify(
                    f"<b>NEW BOUNTY DETECTED</b>\n\n"
                    f"<b>Title:</b> {b_title}\n"
                    f"<b>Reward:</b> {b_reward}\n"
                    f"Auto-submit is OFF. Use /admin/ai-job/run-bounties to evaluate.",
                    buttons=[{"text": "View Bounty", "url": f"https://superteam.fun/bounties/{b_slug}"}],
                )

        _mark_seen([b.get("id") for b in new_bounties if b.get("id")])

    status: dict[str, Any] = {
        "lastCheck": now,
        "openBounties": len(open_listings),
        "newBounties": len(new_bounties),
        "submitted": len(submitted_ids),
        "monitorSubmitEnabled": MONITOR_SUBMIT,
        "listings": compact_listings,
    }
    _save_json(MONITOR_STATUS_PATH, status)
    return status
