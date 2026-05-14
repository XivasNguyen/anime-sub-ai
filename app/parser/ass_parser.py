from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pysubs2


@dataclass(frozen=True)
class SubtitleLine:
    index: int
    start: int
    end: int
    style: str
    text: str
    raw_text: str


@dataclass
class ParsedSubtitle:
    path: Path
    subs: pysubs2.SSAFile
    lines: list[SubtitleLine]


def parse_ass(path: Path) -> ParsedSubtitle:
    subs = pysubs2.load(str(path), encoding="utf-8")
    lines = [
        SubtitleLine(
            index=index,
            start=event.start,
            end=event.end,
            style=event.style,
            text=event.plaintext,
            raw_text=event.text,
        )
        for index, event in enumerate(subs.events, start=1)
    ]
    return ParsedSubtitle(path=path, subs=subs, lines=lines)

