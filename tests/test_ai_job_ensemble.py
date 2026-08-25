import asyncio
from types import SimpleNamespace

from server.ai_job import multi_ai_evaluator as evaluator


def _run(coro):
    return asyncio.run(coro)


def test_ensemble_blends_scores_and_selects_best_proposal(monkeypatch):
    monkeypatch.setenv("BOUNTY_MIN_FIT_SCORE", "7")

    async def fake_openai(prompt):
        return {
            "engine": "openai",
            "available": True,
            "score": 8,
            "proposal": "OpenAI proposal",
            "raw": "",
        }

    async def fake_gemini(prompt):
        return {
            "engine": "gemini",
            "available": True,
            "score": 9,
            "proposal": "Gemini proposal",
            "raw": "",
        }

    async def fake_ollama(prompt):
        return {
            "engine": "ollama",
            "available": True,
            "score": 6,
            "proposal": "Ollama proposal",
            "raw": "",
        }

    monkeypatch.setattr(evaluator, "_call_openai", fake_openai)
    monkeypatch.setattr(evaluator, "_call_gemini", fake_gemini)
    monkeypatch.setattr(evaluator, "_call_ollama", fake_ollama)

    result = _run(evaluator.evaluate_bounty("Test bounty", "Build a useful tool."))

    assert result["ensemble_score"] == 7.7
    assert result["engines_responded"] == 3
    assert result["majority_recommends"] is True
    assert result["best_proposal"] == "Gemini proposal"


def test_single_engine_cannot_trigger_majority_submission(monkeypatch):
    monkeypatch.setenv("BOUNTY_MIN_FIT_SCORE", "7")

    async def scored_openai(prompt):
        return {
            "engine": "openai",
            "available": True,
            "score": 10,
            "proposal": "OpenAI proposal",
            "raw": "",
        }

    async def unavailable(prompt):
        return {"engine": "offline", "available": False, "score": None, "proposal": None, "raw": ""}

    monkeypatch.setattr(evaluator, "_call_openai", scored_openai)
    monkeypatch.setattr(evaluator, "_call_gemini", unavailable)
    monkeypatch.setattr(evaluator, "_call_ollama", unavailable)

    result = _run(evaluator.evaluate_bounty("Test bounty", "Build a useful tool."))

    assert result["engines_responded"] == 1
    assert result["ensemble_score"] == 10.0
    assert result["majority_recommends"] is False


def test_gemini_engine_uses_shared_adapter(monkeypatch):
    calls = {}
    monkeypatch.setattr(evaluator, "GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr(evaluator, "GEMINI_MODEL", "gemini-test")

    async def fake_generate_content_async(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(text="[SCORE: 8/10]\n<PROPOSAL>Gemini proposal</PROPOSAL>")

    monkeypatch.setattr("server.gemini_client.generate_content_async", fake_generate_content_async)

    result = _run(evaluator._call_gemini("Bounty details"))

    assert result["engine"] == "gemini"
    assert result["score"] == 8
    assert result["proposal"] == "Gemini proposal"
    assert calls["api_key"] == "test-gemini-key"
    assert calls["model"] == "gemini-test"
