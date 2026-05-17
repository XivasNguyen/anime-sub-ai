from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.parser.ass_parser import SubtitleLine


@dataclass(frozen=True)
class PromptTerm:
    source: str
    target: str
    note: str = ""
    protected: bool = True


@dataclass(frozen=True)
class PromptContext:
    series_title: str = ""
    summary: str = ""
    spoiler_mode: str = "no_spoiler"
    terms: list[PromptTerm] = field(default_factory=list)
    version: str = "none"


@dataclass(frozen=True)
class AudioLineContext:
    index: int
    japanese_text: str = ""
    confidence: float = 0.0
    overlap_ms: int = 0
    source: str = "none"


@dataclass(frozen=True)
class TranslationChunk:
    lines: list[SubtitleLine]
    context_before: list[SubtitleLine]
    prompt_context: PromptContext = field(default_factory=PromptContext)
    audio_context: dict[int, AudioLineContext] = field(default_factory=dict)


@dataclass(frozen=True)
class TranslationResult:
    index: int
    translated_text: str


class TranslatorProvider(ABC):
    @abstractmethod
    async def translate(self, chunk: TranslationChunk) -> list[TranslationResult]:
        pass

    async def close(self) -> None:
        pass
