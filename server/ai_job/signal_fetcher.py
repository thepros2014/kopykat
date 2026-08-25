"""signal_fetcher.py — Python port of engine/signalFetcher.js.

Fetches live GitHub commit velocity and Helius on-chain Solana metrics
for each narrative defined in narratives.json, then blends them into a
Narrative Momentum Score (NMS = 0.4*GitHub + 0.35*OnChain + 0.25*Social).

Data sources:
  - GitHub REST API v3 (unauthenticated or with GITHUB_TOKEN for higher rate limit)
  - Helius public RPC (getSignaturesForAddress, getRecentPrioritizationFees)
  - Social score is currently mock (0.5) unless a social API is configured.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY", "demo")
HELIUS_RPC = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

GITHUB_HEADERS: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
if GITHUB_TOKEN:
    GITHUB_HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"

HTTP_TIMEOUT = 10.0
MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get(client: httpx.AsyncClient, url: str, **kwargs: Any) -> dict[str, Any] | list | None:
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = await client.get(url, timeout=HTTP_TIMEOUT, **kwargs)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                await asyncio.sleep(2 ** attempt)
                continue
            return None
        except Exception as exc:
            if attempt == MAX_RETRIES:
                logger.debug("GET %s failed: %s", url, exc)
            await asyncio.sleep(1)
    return None


async def _post_rpc(client: httpx.AsyncClient, payload: dict) -> dict | None:
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = await client.post(HELIUS_RPC, json=payload, timeout=HTTP_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            await asyncio.sleep(2 ** attempt)
        except Exception as exc:
            if attempt == MAX_RETRIES:
                logger.debug("RPC call failed: %s", exc)
            await asyncio.sleep(1)
    return None


# ---------------------------------------------------------------------------
# GitHub signal
# ---------------------------------------------------------------------------

async def fetch_github_velocity(client: httpx.AsyncClient, repos: list[str]) -> tuple[float, bool]:
    """Return (normalised_score_0_to_10, is_live) for a list of 'owner/repo' strings."""
    if not repos:
        return 5.0, False

    total_commits = 0
    live_count = 0

    async def repo_commits(repo: str) -> int:
        data = await _get(
            client,
            f"https://api.github.com/repos/{repo}/commits",
            headers=GITHUB_HEADERS,
            params={"per_page": 10, "since": _iso_days_ago(7)},
        )
        if isinstance(data, list):
            return len(data)
        return 0

    results = await asyncio.gather(*[repo_commits(r) for r in repos], return_exceptions=True)
    for r in results:
        if isinstance(r, int):
            total_commits += r
            if r > 0:
                live_count += 1

    is_live = live_count > 0
    # Normalise: 50+ commits in 7 days across repos = score 10
    score = min(10.0, round((total_commits / max(len(repos), 1)) * 2.0, 2))
    return score, is_live


def _iso_days_ago(days: int) -> str:
    import datetime
    t = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Helius on-chain signal
# ---------------------------------------------------------------------------

async def fetch_onchain_activity(
    client: httpx.AsyncClient, addresses: list[str]
) -> tuple[float, bool, int]:
    """Return (score_0_to_10, is_live, recent_sig_count)."""
    if not addresses:
        return 5.0, False, 0

    total_sigs = 0
    live = False

    async def addr_sigs(address: str) -> int:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [address, {"limit": 20}],
        }
        data = await _post_rpc(client, payload)
        if data and isinstance(data.get("result"), list):
            return len(data["result"])
        return 0

    results = await asyncio.gather(*[addr_sigs(a) for a in addresses], return_exceptions=True)
    for r in results:
        if isinstance(r, int) and r > 0:
            total_sigs += r
            live = True

    score = min(10.0, round(total_sigs * 0.5, 2))
    return score, live, total_sigs


async def fetch_helius_network_stats(client: httpx.AsyncClient) -> dict[str, Any]:
    """Return TPS and slot height from the Helius RPC."""
    try:
        slot_data = await _post_rpc(client, {"jsonrpc": "2.0", "id": 1, "method": "getSlot"})
        perf_data = await _post_rpc(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "getRecentPerformanceSamples", "params": [1]},
        )
        slot = slot_data["result"] if slot_data and "result" in slot_data else 0
        tps = 0.0
        if perf_data and isinstance(perf_data.get("result"), list) and perf_data["result"]:
            sample = perf_data["result"][0]
            secs = sample.get("samplePeriodSecs", 1)
            tps = round(sample.get("numTransactions", 0) / max(secs, 1), 1)
        return {"tps": tps, "slotHeight": slot, "dataTag": "[LIVE]"}
    except Exception:
        return {"tps": 2800.0, "slotHeight": 0, "dataTag": "[MOCK]"}


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

async def fetch_all_signals(narratives: list[dict]) -> dict[str, Any]:
    """Fetch GitHub + on-chain signals for all narratives and compute NMS scores."""
    start = time.monotonic()

    async with httpx.AsyncClient() as client:
        net_stats = await fetch_helius_network_stats(client)

        narrative_scores = []
        for narrative in narratives:
            repos: list[str] = narrative.get("githubRepos", [])
            addresses: list[str] = narrative.get("onchainAddresses", [])

            github_score, github_live = await fetch_github_velocity(client, repos)
            onchain_score, onchain_live, sig_count = await fetch_onchain_activity(client, addresses)
            social_score = float(narrative.get("mockSocialScore", 5.0))

            # NMS = 0.4*GitHub + 0.35*OnChain + 0.25*Social  (each 0-10, NMS 0-100)
            nms = round(
                (github_score * 0.4 + onchain_score * 0.35 + social_score * 0.25) * 10, 1
            )

            narrative_scores.append({
                "narrativeId": narrative.get("id", "unknown"),
                "title": narrative.get("title", ""),
                "momentumScore": nms,
                "signals": {
                    "githubVelocity": github_score,
                    "onchainSpikes": onchain_score,
                    "kolSentiment": social_score,
                },
                "dataSourceStatus": {
                    "github": "[LIVE]" if github_live else "[MOCK]",
                    "onchain": "[LIVE]" if onchain_live else "[MOCK]",
                    "social": "[MOCK]",
                    "recentSigCount": sig_count,
                },
                "repoTelemetry": [{"repo": r, "commitLive": github_live} for r in repos],
            })

        if narrative_scores:
            avg_nms = round(sum(n["momentumScore"] for n in narrative_scores) / len(narrative_scores), 1)
            total_pts = len(narrative_scores) * 3
            live_pts = sum(
                (1 if n["dataSourceStatus"]["github"] == "[LIVE]" else 0)
                + (1 if n["dataSourceStatus"]["onchain"] == "[LIVE]" else 0)
                for n in narrative_scores
            )
            live_pct = round(live_pts / max(total_pts, 1) * 100, 1)
        else:
            avg_nms, live_pct = 0.0, 0.0

    elapsed_ms = round((time.monotonic() - start) * 1000)
    return {
        "generatedAt": _iso_now(),
        "elapsedMs": elapsed_ms,
        "totalNarratives": len(narrative_scores),
        "avgMomentumScore": avg_nms,
        "liveCoveragePercent": live_pct,
        "heliusNetworkStats": net_stats,
        "narrativeScores": narrative_scores,
        "topContracts": [],  # populated by signal_engine if needed
    }


def _iso_now() -> str:
    import datetime
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
