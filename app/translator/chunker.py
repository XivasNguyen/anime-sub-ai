from __future__ import annotations

from app.parser.ass_parser import SubtitleLine
from app.translator.base import AudioLineContext, PromptContext, TranslationChunk


def chunk_subtitles(
    lines: list[SubtitleLine],
    chunk_size: int = 12,
    overlap_lines: int = 2,
    prompt_context: PromptContext | None = None,
    audio_context: dict[int, AudioLineContext] | None = None,
) -> list[TranslationChunk]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    if overlap_lines < 0:
        raise ValueError("overlap_lines must be zero or greater")

    chunks: list[TranslationChunk] = []
    for start in range(0, len(lines), chunk_size):
        current = lines[start : start + chunk_size]
        context_start = max(0, start - overlap_lines)
        chunks.append(
            TranslationChunk(
                lines=current,
                context_before=lines[context_start:start],
                prompt_context=prompt_context or PromptContext(),
                audio_context=audio_context or {},
            )
        )
    return chunks
