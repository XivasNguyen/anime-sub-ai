from __future__ import annotations

import re
from dataclasses import dataclass


ASS_TAG_RE = re.compile(r"\{\\[^{}]*\}")
PLACEHOLDER_RE = re.compile(r"\[\[ASS_TAG_(\d{2})\]\]")


@dataclass(frozen=True)
class MaskedText:
    text: str
    tags: tuple[str, ...]


def mask_ass_text(text: str) -> MaskedText:
    tags: list[str] = []

    def replace(match: re.Match[str]) -> str:
        tags.append(match.group(0))
        return f"[[ASS_TAG_{len(tags) - 1:02d}]]"

    return MaskedText(text=ASS_TAG_RE.sub(replace, text), tags=tuple(tags))


def restore_ass_text(text: str, original: str) -> str:
    masked = mask_ass_text(original)

    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1))
        if index >= len(masked.tags):
            return match.group(0)
        return masked.tags[index]

    restored = PLACEHOLDER_RE.sub(replace, text)
    missing = [tag for tag in masked.tags if tag not in restored]
    if missing:
        restored = "".join(missing) + restored
    return restored
