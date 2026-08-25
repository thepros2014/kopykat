"""signal_engine.py — Orchestrates a full signal engine run and persists results.

Python equivalent of engine/runEngine.js + engine/scheduler.js combined.
Results are stored in server/ai_job/data/ as JSON files and exposed via
KopyKat API endpoints instead of being written to a local filesystem only.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any

from .signal_fetcher import fetch_all_signals

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
NARRATIVES_PATH = _HERE / "narratives.json"
DATA_DIR = _HERE / "data"
SIGNALS_PATH = DATA_DIR / "signals.json"
ENGINE_META_PATH = DATA_DIR / "engine_meta.json"
HISTORY_DIR = DATA_DIR / "history"

_run_index = 0  # incremented each scheduled run


def load_narratives() -> list[dict]:
    """Load narrative definitions from the bundled narratives.json."""
    try:
        with open(NARRATIVES_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("narratives"), list):
            return data["narratives"]
        return []
    except Exception as exc:
        logger.error("Failed to load narratives.json: %s", exc)
        return []


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)


def get_latest_signals() -> dict[str, Any] | None:
    """Return the most recent signals.json payload, or None if not yet run."""
    try:
        with open(SIGNALS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.error("Failed to read signals.json: %s", exc)
        return None


def get_engine_meta() -> dict[str, Any] | None:
    """Return the engine_meta.json payload."""
    try:
        with open(ENGINE_META_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.error("Failed to read engine_meta.json: %s", exc)
        return None


def get_history(date_str: str) -> list[dict] | None:
    """Return historical snapshots for a given YYYY-MM-DD date."""
    history_file = HISTORY_DIR / f"signals_{date_str}.json"
    try:
        with open(history_file, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.error("Failed to read history file %s: %s", history_file, exc)
        return None


async def run_once() -> dict[str, Any]:
    """Execute a full signal engine run and persist results. Returns the signals payload."""
    global _run_index
    _run_index += 1
    run_start = datetime.datetime.utcnow()

    logger.info("AI Signal Engine run #%d starting", _run_index)
    narratives = load_narratives()
    if not narratives:
        logger.warning("No narratives loaded — signal engine run skipped.")
        return {}

    signals_data = await fetch_all_signals(narratives)

    _ensure_dirs()

    # Write signals.json
    with open(SIGNALS_PATH, "w", encoding="utf-8") as fh:
        json.dump(signals_data, fh, indent=2)

    # Build engine_meta
    live_sources: list[str] = []
    mock_sources: list[str] = []
    for n in signals_data.get("narrativeScores", []):
        s = n.get("dataSourceStatus", {})
        base = n.get("narrativeId", "unknown")
        (live_sources if s.get("github") == "[LIVE]" else mock_sources).append(f"{base}:github")
        (live_sources if s.get("onchain") == "[LIVE]" else mock_sources).append(f"{base}:onchain")
        mock_sources.append(f"{base}:social")

    helius = signals_data.get("heliusNetworkStats", {})
    (live_sources if helius.get("dataTag") == "[LIVE]" else mock_sources).append("helius:tps")

    total_pts = len(live_sources) + len(mock_sources)
    next_run = run_start + datetime.timedelta(hours=6)

    engine_meta = {
        "lastRunAt": run_start.isoformat() + "Z",
        "schedulerRunIndex": _run_index,
        "elapsedMs": signals_data.get("elapsedMs", 0),
        "totalNarratives": signals_data.get("totalNarratives", 0),
        "avgMomentumScore": signals_data.get("avgMomentumScore", 0),
        "liveCoveragePercent": signals_data.get("liveCoveragePercent", 0),
        "totalDataPoints": total_pts,
        "liveDataPoints": len(live_sources),
        "mockDataPoints": len(mock_sources),
        "liveDataSources": live_sources,
        "mockDataSources": mock_sources,
        "heliusTps": helius.get("tps", 0),
        "heliusTpsLive": helius.get("dataTag") == "[LIVE]",
        "heliusSlotHeight": helius.get("slotHeight", 0),
        "nextRunAt": next_run.isoformat() + "Z",
    }

    with open(ENGINE_META_PATH, "w", encoding="utf-8") as fh:
        json.dump(engine_meta, fh, indent=2)

    # Append daily history snapshot
    date_str = run_start.strftime("%Y-%m-%d")
    history_file = HISTORY_DIR / f"signals_{date_str}.json"
    try:
        with open(history_file, "r", encoding="utf-8") as fh:
            history: list = json.load(fh)
        if not isinstance(history, list):
            history = []
    except FileNotFoundError:
        history = []

    snapshot = {
        "timestamp": run_start.isoformat() + "Z",
        "schedulerRunIndex": _run_index,
        "elapsedMs": signals_data.get("elapsedMs", 0),
        "avgMomentumScore": signals_data.get("avgMomentumScore", 0),
        "liveCoveragePercent": signals_data.get("liveCoveragePercent", 0),
        "heliusTps": helius.get("tps", 0),
        "heliusSlotHeight": helius.get("slotHeight", 0),
        "heliusTpsLive": helius.get("dataTag") == "[LIVE]",
        "narratives": [
            {
                "id": n.get("narrativeId"),
                "title": n.get("title"),
                "nms": n.get("momentumScore"),
                "github": n.get("signals", {}).get("githubVelocity"),
                "onchain": n.get("signals", {}).get("onchainSpikes"),
                "social": n.get("signals", {}).get("kolSentiment"),
                "githubLive": n.get("dataSourceStatus", {}).get("github") == "[LIVE]",
                "onchainLive": n.get("dataSourceStatus", {}).get("onchain") == "[LIVE]",
                "recentSigCount": n.get("dataSourceStatus", {}).get("recentSigCount", 0),
            }
            for n in signals_data.get("narrativeScores", [])
        ],
    }
    history.append(snapshot)

    with open(history_file, "w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2)

    logger.info(
        "AI Signal Engine run #%d complete — avg NMS: %.1f | live coverage: %.1f%% | elapsed: %dms",
        _run_index,
        signals_data.get("avgMomentumScore", 0),
        signals_data.get("liveCoveragePercent", 0),
        signals_data.get("elapsedMs", 0),
    )
    return signals_data


def run_signal_engine_sync() -> None:
    """Synchronous wrapper for use with APScheduler (which calls sync functions)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(run_once())
        else:
            loop.run_until_complete(run_once())
    except Exception:
        logger.exception("Signal engine scheduler run failed")
