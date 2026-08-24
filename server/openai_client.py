"""Small lifecycle-safe adapter for the OpenAI Responses API."""

from __future__ import annotations

import base64
from typing import Any

from openai import AsyncOpenAI, OpenAI


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _response_text(response: Any) -> str:
    text = _field(response, "output_text", "")
    if isinstance(text, str) and text.strip():
        return text.strip()

    chunks: list[str] = []
    for item in _field(response, "output", []) or []:
        for content in _field(item, "content", []) or []:
            content_text = _field(content, "text", "")
            if isinstance(content_text, str) and content_text:
                chunks.append(content_text)
    return "".join(chunks).strip()


def _usage_tokens(response: Any) -> int:
    usage = _field(response, "usage")
    if usage is None:
        return 0
    total = _field(usage, "total_tokens")
    if total is not None:
        return int(total)
    return int(_field(usage, "input_tokens", 0) or 0) + int(
        _field(usage, "output_tokens", 0) or 0
    )


def _request_kwargs(
    *,
    model: str,
    input_value: Any,
    system_instruction: str | None,
    max_output_tokens: int | None,
    temperature: float | None,
    json_mode: bool,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "model": model,
        "input": input_value,
        # Do not retain generated marketing content with the provider by
        # default. Applications that need provider-side state must opt in.
        "store": False,
    }
    if system_instruction:
        values["instructions"] = system_instruction
    if max_output_tokens is not None:
        values["max_output_tokens"] = max_output_tokens
    if temperature is not None:
        values["temperature"] = temperature
    if json_mode:
        values["text"] = {"format": {"type": "json_object"}}
    return values


async def generate_text_async(
    *,
    api_key: str,
    model: str,
    input_value: Any,
    system_instruction: str | None = None,
    max_output_tokens: int | None = None,
    temperature: float | None = None,
    json_mode: bool = False,
) -> tuple[str, int]:
    """Generate text and close the SDK transport after the request."""

    client = AsyncOpenAI(api_key=api_key, timeout=30.0, max_retries=0)
    try:
        response = await client.responses.create(
            **_request_kwargs(
                model=model,
                input_value=input_value,
                system_instruction=system_instruction,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                json_mode=json_mode,
            )
        )
        return _response_text(response), _usage_tokens(response)
    finally:
        await client.close()


def generate_text(
    *,
    api_key: str,
    model: str,
    input_value: Any,
    system_instruction: str | None = None,
    max_output_tokens: int | None = None,
    temperature: float | None = None,
    json_mode: bool = False,
) -> tuple[str, int]:
    """Generate text and close the SDK transport after the request."""

    client = OpenAI(api_key=api_key, timeout=30.0, max_retries=0)
    try:
        response = client.responses.create(
            **_request_kwargs(
                model=model,
                input_value=input_value,
                system_instruction=system_instruction,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                json_mode=json_mode,
            )
        )
        return _response_text(response), _usage_tokens(response)
    finally:
        client.close()


def generate_vision_json(
    *,
    api_key: str,
    model: str,
    image_bytes: bytes,
    mime_type: str,
    prompt: str,
    max_output_tokens: int = 2500,
) -> tuple[str, int]:
    """Analyze an image and return structured JSON text plus usage tokens."""

    encoded = base64.b64encode(image_bytes).decode("ascii")
    input_value = [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {
                    "type": "input_image",
                    "image_url": f"data:{mime_type};base64,{encoded}",
                },
            ],
        }
    ]
    return generate_text(
        api_key=api_key,
        model=model,
        input_value=input_value,
        max_output_tokens=max_output_tokens,
        json_mode=True,
    )
