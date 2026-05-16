from __future__ import annotations

import asyncio

from openai import AsyncOpenAI

from app.translator.base import TranslationChunk, TranslationResult, TranslatorProvider
from app.translator.json_response import TranslationResponseError, parse_translation_response
from app.translator.openai_compat import normalize_openai_base_url
from app.translator.prompt_builder import build_compact_user_prompt


class LMStudioTranslator(TranslatorProvider):
    def __init__(self, base_url: str, model: str, api_key: str = "lm-studio", retry_count: int = 3) -> None:
        self.base_url = normalize_openai_base_url(base_url)
        self.client = AsyncOpenAI(base_url=self.base_url, api_key=api_key or "lm-studio")
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
            "Translate anime subtitle text from English to natural Vietnamese. "
            "ASS tags are masked as placeholders like [[ASS_TAG_00]]; preserve placeholders exactly. "
            "Use the knowledge and glossary terms when relevant. "
            "Preserve names and honorifics when appropriate. "
            "Return only valid JSON with key translations. "
            "No reasoning, no explanations, no markdown."
        )
        user_prompt = f"{build_compact_user_prompt(chunk)}\n/no_think"
        response = await self.client.chat.completions.create(
            model=self.model,
            response_format={"type": "text"},
            temperature=0.2,
            max_tokens=8192,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise TranslationResponseError("LM Studio returned an empty response.")
        return parse_translation_response(content, {line.index for line in chunk.lines})

    async def close(self) -> None:
        await self.client.close()
