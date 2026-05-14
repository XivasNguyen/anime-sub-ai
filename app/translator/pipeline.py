from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from app.parser.ass_parser import SubtitleLine
from app.cache.sqlite_cache import TranslationCache, chunk_cache_key
from app.translator.ass_mask import restore_ass_text
from app.translator.base import PromptContext, TranslationChunk, TranslationResult, TranslatorProvider
from app.translator.chunker import chunk_subtitles
from app.translator.prompt_builder import PROMPT_VERSION


@dataclass
class PipelineStats:
    chunk_count: int = 0
    completed_chunks: int = 0
    retry_splits: int = 0
    chunk_timings: list[float] = field(default_factory=list)


async def translate_lines(
    lines: list[SubtitleLine],
    provider: TranslatorProvider,
    chunk_size: int,
    overlap_lines: int,
    max_concurrency: int,
    prompt_context: PromptContext | None = None,
    prompt_context_builder: Callable[[list[SubtitleLine]], PromptContext] | None = None,
    cache: TranslationCache | None = None,
    provider_name: str = "",
    model: str = "",
    force_retranslate: bool = False,
    stats: PipelineStats | None = None,
) -> dict[int, str]:
    chunks = chunk_subtitles(
        lines,
        chunk_size=chunk_size,
        overlap_lines=overlap_lines,
        prompt_context=prompt_context,
    )
    if prompt_context_builder is not None:
        chunks = [
            TranslationChunk(
                lines=chunk.lines,
                context_before=chunk.context_before,
                prompt_context=prompt_context_builder([*chunk.context_before, *chunk.lines]),
            )
            for chunk in chunks
        ]
    if stats is not None:
        stats.chunk_count = len(chunks)
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def translate_chunk(chunk_index: int) -> list[TranslationResult]:
        async with semaphore:
            started = time.perf_counter()
            print(f"Translating chunk {chunk_index + 1}/{len(chunks)}")
            result = await _translate_chunk_with_cache(
                provider,
                chunks[chunk_index],
                cache=cache,
                provider_name=provider_name,
                model=model,
                force_retranslate=force_retranslate,
                stats=stats,
            )
            elapsed = time.perf_counter() - started
            if stats is not None:
                stats.completed_chunks += 1
                stats.chunk_timings.append(elapsed)
            print(f"Completed chunk {chunk_index + 1}/{len(chunks)} in {elapsed:.1f}s")
            return result

    grouped = await asyncio.gather(*(translate_chunk(index) for index in range(len(chunks))))
    translations: dict[int, str] = {}
    for results in grouped:
        for result in results:
            source = next((line for line in lines if line.index == result.index), None)
            translations[result.index] = (
                restore_ass_text(result.translated_text, source.raw_text) if source is not None else result.translated_text
            )
    return translations


async def _translate_chunk_with_cache(
    provider: TranslatorProvider,
    chunk: TranslationChunk,
    *,
    cache: TranslationCache | None,
    provider_name: str,
    model: str,
    force_retranslate: bool,
    stats: PipelineStats | None,
) -> list[TranslationResult]:
    key = ""
    if cache is not None:
        key = chunk_cache_key(
            chunk,
            provider=provider_name,
            model=model,
            prompt_version=PROMPT_VERSION,
            glossary_version=chunk.prompt_context.version,
            ass_version="ass-mask-v1",
        )
        if not force_retranslate:
            cached = cache.get_chunk(key)
            if cached is not None:
                return cached
    results = await _translate_chunk_resilient(provider, chunk, stats=stats)
    if cache is not None:
        cache.put_chunk(
            key,
            results,
            {
                "provider": provider_name,
                "model": model,
                "prompt_version": PROMPT_VERSION,
                "glossary_version": chunk.prompt_context.version,
            },
        )
    return results


async def _translate_chunk_resilient(
    provider: TranslatorProvider,
    chunk: TranslationChunk,
    stats: PipelineStats | None = None,
) -> list[TranslationResult]:
    try:
        return await provider.translate(chunk)
    except Exception:
        if len(chunk.lines) <= 1:
            raise

    midpoint = len(chunk.lines) // 2
    left = TranslationChunk(
        lines=chunk.lines[:midpoint],
        context_before=chunk.context_before,
        prompt_context=chunk.prompt_context,
    )
    right = TranslationChunk(
        lines=chunk.lines[midpoint:],
        context_before=[*chunk.context_before, *chunk.lines[:midpoint]],
        prompt_context=chunk.prompt_context,
    )
    print(f"Retrying failed chunk as {len(left.lines)} + {len(right.lines)} lines")
    if stats is not None:
        stats.retry_splits += 1
    left_results = await _translate_chunk_resilient(provider, left, stats=stats)
    right_results = await _translate_chunk_resilient(provider, right, stats=stats)
    return [*left_results, *right_results]
