from __future__ import annotations

import asyncio
import time

from app.parser.ass_parser import SubtitleLine
from app.translator.base import TranslationChunk, TranslationResult, TranslatorProvider
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
            started = time.perf_counter()
            print(f"Translating chunk {chunk_index + 1}/{len(chunks)}")
            result = await _translate_chunk_resilient(provider, chunks[chunk_index])
            elapsed = time.perf_counter() - started
            print(f"Completed chunk {chunk_index + 1}/{len(chunks)} in {elapsed:.1f}s")
            return result

    grouped = await asyncio.gather(*(translate_chunk(index) for index in range(len(chunks))))
    translations: dict[int, str] = {}
    for results in grouped:
        for result in results:
            translations[result.index] = result.translated_text
    return translations


async def _translate_chunk_resilient(
    provider: TranslatorProvider,
    chunk: TranslationChunk,
) -> list[TranslationResult]:
    try:
        return await provider.translate(chunk)
    except Exception:
        if len(chunk.lines) <= 1:
            raise

    midpoint = len(chunk.lines) // 2
    left = TranslationChunk(lines=chunk.lines[:midpoint], context_before=chunk.context_before)
    right = TranslationChunk(
        lines=chunk.lines[midpoint:],
        context_before=[*chunk.context_before, *chunk.lines[:midpoint]],
    )
    print(f"Retrying failed chunk as {len(left.lines)} + {len(right.lines)} lines")
    left_results = await _translate_chunk_resilient(provider, left)
    right_results = await _translate_chunk_resilient(provider, right)
    return [*left_results, *right_results]
