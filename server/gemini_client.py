"""Small, lifecycle-safe adapter for the supported Google Gen AI SDK."""

from __future__ import annotations

from typing import Any

from google import genai
from google.genai import types


def _config(
    *,
    system_instruction: str | None = None,
    max_output_tokens: int | None = None,
    temperature: float | None = None,
    response_mime_type: str | None = None,
) -> types.GenerateContentConfig | None:
    values: dict[str, Any] = {}
    if system_instruction:
        values["system_instruction"] = system_instruction
    if max_output_tokens is not None:
        values["max_output_tokens"] = max_output_tokens
    if temperature is not None:
        values["temperature"] = temperature
    if response_mime_type:
        values["response_mime_type"] = response_mime_type
    return types.GenerateContentConfig(**values) if values else None


async def generate_content_async(
    *,
    api_key: str,
    model: str,
    contents: Any,
    system_instruction: str | None = None,
    max_output_tokens: int | None = None,
    temperature: float | None = None,
    response_mime_type: str | None = None,
) -> Any:
    """Generate content and always close the SDK's async transport."""

    client = genai.Client(api_key=api_key)
    try:
        return await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=_config(
                system_instruction=system_instruction,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                response_mime_type=response_mime_type,
            ),
        )
    finally:
        await client.aio.aclose()


def generate_content(
    *,
    api_key: str,
    model: str,
    contents: Any,
    system_instruction: str | None = None,
    max_output_tokens: int | None = None,
    temperature: float | None = None,
    response_mime_type: str | None = None,
) -> Any:
    """Generate content and always close the SDK's sync transport."""

    client = genai.Client(api_key=api_key)
    try:
        return client.models.generate_content(
            model=model,
            contents=contents,
            config=_config(
                system_instruction=system_instruction,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                response_mime_type=response_mime_type,
            ),
        )
    finally:
        client.close()


def image_part(image_bytes: bytes, mime_type: str) -> types.Part:
    """Build a typed image part without exposing raw provider objects elsewhere."""

    return types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
