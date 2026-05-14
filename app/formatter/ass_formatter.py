from __future__ import annotations

import copy
from pathlib import Path

import pysubs2

from app.parser.ass_parser import ParsedSubtitle


def rebuild_ass(parsed: ParsedSubtitle, translations: dict[int, str], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    translated = copy.deepcopy(parsed.subs)
    for index, event in enumerate(translated.events, start=1):
        if index in translations:
            event.text = translations[index]

    translated.save(str(output_path), encoding="utf-8", format_="ass")
    pysubs2.load(str(output_path), encoding="utf-8")
    return output_path
