from __future__ import annotations

import asyncio

from app.parser.ass_parser import SubtitleLine
from app.translator.base import TranslationResult, TranslatorProvider
from app.translator.chunker import chunk_subtitles


async def translate_lines(
    lines: list[SubtitleLine],
    provider: TranslatorProvider,
    chunk_size: int,
    overlap_lines: int,
    max_concurrency: int,
) -> dict[int, str]:
    chunks = chunk_subtitles(lines, chunk_size=chunk_size, overlap_lines=overlap_lines)
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def translate_chunk(chunk_index: int) -> list[TranslationResult]:
        async with semaphore:
            print(f"Translating chunk {chunk_index + 1}/{len(chunks)}")
            return await provider.translate(chunks[chunk_index])

    grouped = await asyncio.gather(*(translate_chunk(index) for index in range(len(chunks))))
    translations: dict[int, str] = {}
    for results in grouped:
        for result in results:
            translations[result.index] = result.translated_text
    return translations

