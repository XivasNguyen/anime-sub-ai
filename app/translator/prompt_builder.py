from __future__ import annotations

import json

from app.parser.ass_parser import SubtitleLine
from app.translator.base import TranslationChunk


SYSTEM_PROMPT = """You translate anime subtitles from English into natural Vietnamese.
Preserve anime tone, honorifics, jokes, sarcasm, emotional nuance, names, and world terms.
Use conversational Vietnamese, not robotic or overly formal wording.
Preserve every ASS override tag exactly, including braces, order, spelling, and placement when possible.
Return strict JSON only. Keep the same number of translated lines as the input lines.
Do not translate context lines unless they also appear in lines_to_translate."""


def _line_payload(line: SubtitleLine) -> dict[str, object]:
    return {
        "index": line.index,
        "start_ms": line.start,
        "end_ms": line.end,
        "style": line.style,
        "text": line.raw_text,
    }


def build_user_prompt(chunk: TranslationChunk) -> str:
    payload = {
        "context_before": [_line_payload(line) for line in chunk.context_before],
        "lines_to_translate": [_line_payload(line) for line in chunk.lines],
        "response_schema": {
            "translations": [
                {"index": "same integer index", "translated_text": "Vietnamese ASS text"}
            ]
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_compact_user_prompt(chunk: TranslationChunk) -> str:
    payload = {
        "context_before": [
            {"index": line.index, "text": line.raw_text}
            for line in chunk.context_before
        ],
        "lines_to_translate": [
            {"index": line.index, "text": line.raw_text}
            for line in chunk.lines
        ],
        "required_output": {
            "translations": [
                {"index": "integer from lines_to_translate", "translated_text": "Vietnamese ASS text"}
            ]
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
