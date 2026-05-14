from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.parser.ass_parser import SubtitleLine


@dataclass(frozen=True)
class TranslationChunk:
    lines: list[SubtitleLine]
    context_before: list[SubtitleLine]


@dataclass(frozen=True)
class TranslationResult:
    index: int
    translated_text: str


class TranslatorProvider(ABC):
    @abstractmethod
    async def translate(self, chunk: TranslationChunk) -> list[TranslationResult]:
        pass

