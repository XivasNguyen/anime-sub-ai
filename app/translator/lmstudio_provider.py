from __future__ import annotations

import asyncio

from openai import AsyncOpenAI

from app.translator.base import TranslationChunk, TranslationResult, TranslatorProvider
from app.translator.json_response import TranslationResponseError, parse_translation_response
from app.translator.prompt_builder import SYSTEM_PROMPT, build_user_prompt


class LMStudioTranslator(TranslatorProvider):
    def __init__(self, base_url: str, model: str, api_key: str = "lm-studio", retry_count: int = 3) -> None:
        self.client = AsyncOpenAI(base_url=base_url.rstrip("/"), api_key=api_key or "lm-studio")
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
        system_prompt = (
            f"{SYSTEM_PROMPT}\n"
            "Do not include reasoning, analysis, explanations, markdown, or code fences. "
            "Return only the final JSON object."
        )
        user_prompt = f"{build_user_prompt(chunk)}\n/no_think"
        response = await self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "text"},
            temperature=0.2,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise TranslationResponseError("LM Studio returned an empty response.")
        return parse_translation_response(content, {line.index for line in chunk.lines})
