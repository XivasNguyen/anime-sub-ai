from __future__ import annotations

import asyncio

import httpx

from app.translator.base import TranslationChunk, TranslationResult, TranslatorProvider
from app.translator.json_response import TranslationResponseError, parse_translation_response
from app.translator.prompt_builder import SYSTEM_PROMPT, build_user_prompt


class OllamaTranslator(TranslatorProvider):
    def __init__(self, base_url: str, model: str, retry_count: int = 3, timeout: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.retry_count = retry_count
        self.timeout = timeout

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
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(chunk)},
            ],
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content")
        if not isinstance(content, str) or not content:
            raise TranslationResponseError("Ollama returned an empty response.")
        return parse_translation_response(content, {line.index for line in chunk.lines})

