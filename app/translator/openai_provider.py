from __future__ import annotations

import asyncio
import json
from typing import Any

from openai import AsyncOpenAI

from app.translator.base import TranslationChunk, TranslationResult, TranslatorProvider
from app.translator.prompt_builder import SYSTEM_PROMPT, build_user_prompt


class TranslationResponseError(RuntimeError):
    pass


class OpenAITranslator(TranslatorProvider):
    def __init__(self, api_key: str, model: str, retry_count: int = 3) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY or config openai.api_key.")
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.retry_count = retry_count

    async def translate(self, chunk: TranslationChunk) -> list[TranslationResult]:
        last_error: Exception | None = None
        for attempt in range(1, self.retry_count + 1):
            try:
                return await self._translate_once(chunk)
            except Exception as exc:
                last_error = exc
                if attempt < self.retry_count:
                    await asyncio.sleep(min(2**attempt, 8))
        assert last_error is not None
        raise last_error

    async def _translate_once(self, chunk: TranslationChunk) -> list[TranslationResult]:
        response = await self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(chunk)},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise TranslationResponseError("OpenAI returned an empty response.")
        return parse_translation_response(content, {line.index for line in chunk.lines})


def parse_translation_response(content: str, expected_indexes: set[int]) -> list[TranslationResult]:
    try:
        data: Any = json.loads(content)
    except json.JSONDecodeError as exc:
        raise TranslationResponseError(f"Malformed translation JSON: {exc}") from exc

    translations = data.get("translations") if isinstance(data, dict) else None
    if not isinstance(translations, list):
        raise TranslationResponseError("Translation JSON must contain a translations list.")

    results: list[TranslationResult] = []
    seen: set[int] = set()
    for item in translations:
        if not isinstance(item, dict):
            raise TranslationResponseError("Each translation entry must be an object.")
        index = item.get("index")
        translated_text = item.get("translated_text")
        if not isinstance(index, int) or not isinstance(translated_text, str):
            raise TranslationResponseError("Each translation requires integer index and string translated_text.")
        if index in seen:
            raise TranslationResponseError(f"Duplicate translation index: {index}")
        if index not in expected_indexes:
            raise TranslationResponseError(f"Unexpected translation index: {index}")
        seen.add(index)
        results.append(TranslationResult(index=index, translated_text=translated_text))

    missing = expected_indexes - seen
    if missing:
        raise TranslationResponseError(f"Missing translations for indexes: {sorted(missing)}")
    return sorted(results, key=lambda result: result.index)

