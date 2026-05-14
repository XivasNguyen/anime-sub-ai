from __future__ import annotations

import asyncio

from openai import AsyncOpenAI

from app.translator.base import TranslationChunk, TranslationResult, TranslatorProvider
from app.translator.json_response import TranslationResponseError, parse_translation_response
from app.translator.prompt_builder import SYSTEM_PROMPT, build_user_prompt


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

    async def close(self) -> None:
        await self.client.close()
