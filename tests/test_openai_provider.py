from types import SimpleNamespace

import pytest

from server import ai_engine, marketing, openai_client


@pytest.mark.asyncio
async def test_openai_adapter_uses_responses_api_and_closes_transport(monkeypatch):
    calls = {}

    class FakeResponses:
        async def create(self, **kwargs):
            calls["request"] = kwargs
            return SimpleNamespace(
                output_text='{"variations":["draft"]}',
                usage=SimpleNamespace(total_tokens=17),
            )

    class FakeClient:
        def __init__(self, **kwargs):
            calls["client"] = kwargs
            self.responses = FakeResponses()

        async def close(self):
            calls["closed"] = True

    monkeypatch.setattr(openai_client, "AsyncOpenAI", FakeClient)

    text, tokens = await openai_client.generate_text_async(
        api_key="test-openai-key",
        model="gpt-test",
        input_value="Write a draft",
        system_instruction="Return JSON",
        max_output_tokens=80,
        json_mode=True,
    )

    assert text == '{"variations":["draft"]}'
    assert tokens == 17
    assert calls["client"] == {"api_key": "test-openai-key", "timeout": 30.0, "max_retries": 0}
    assert calls["request"]["model"] == "gpt-test"
    assert calls["request"]["store"] is False
    assert calls["request"]["instructions"] == "Return JSON"
    assert calls["request"]["text"] == {"format": {"type": "json_object"}}
    assert calls["closed"] is True


@pytest.mark.asyncio
async def test_ai_engine_openai_path_delegates_to_shared_adapter(monkeypatch):
    captured = {}

    async def fake_generate(**kwargs):
        captured.update(kwargs)
        return '{"variations":["ok"]}', 9

    monkeypatch.setattr("server.openai_client.generate_text_async", fake_generate)
    monkeypatch.setattr(ai_engine, "OPENAI_API_KEY", "test-openai-key")

    text, tokens = await ai_engine._generate_openai("prompt", 120)

    assert text == '{"variations":["ok"]}'
    assert tokens == 9
    assert captured["api_key"] == "test-openai-key"
    assert captured["max_output_tokens"] == 120
    assert captured["json_mode"] is True


@pytest.mark.asyncio
async def test_scheduled_marketing_can_use_openai_without_external_test_egress(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("ENVIRONMENT", "production")

    captured = {}

    async def fake_generate(**kwargs):
        captured.update(kwargs)
        return "drafted opportunity reply", 12

    monkeypatch.setattr(marketing, "generate_text_async", fake_generate)

    result = await marketing._generate_marketing_text(
        "Draft a helpful response",
        max_output_tokens=90,
    )

    assert result == "drafted opportunity reply"
    assert captured["api_key"] == "test-openai-key"
    assert captured["model"] == "gpt-4o-mini"
    assert captured["max_output_tokens"] == 90


@pytest.mark.asyncio
async def test_scheduled_marketing_does_not_call_openai_in_testing(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("ENVIRONMENT", "testing")

    async def fail_if_called(**kwargs):
        raise AssertionError("OpenAI must not be contacted during tests")

    monkeypatch.setattr(marketing, "generate_text_async", fail_if_called)

    result = await marketing._generate_marketing_text("Draft a reply")

    assert result == ""
