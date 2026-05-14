from __future__ import annotations

import json

from app.parser.ass_parser import SubtitleLine
from app.translator.ass_mask import mask_ass_text
from app.translator.base import TranslationChunk


PROMPT_VERSION = "2026-05-14.kb-glossary-ass-mask.v1"

SYSTEM_PROMPT = """You translate anime subtitles from English into natural Vietnamese.
Preserve anime tone, honorifics, jokes, sarcasm, emotional nuance, names, and world terms.
Use conversational Vietnamese, not robotic or overly formal wording.
Use provided knowledge and glossary terms when they are relevant to a line.
Protected glossary terms must remain consistent with their target values.
ASS override tags are replaced with placeholders like [[ASS_TAG_00]].
Preserve every placeholder exactly and keep its approximate placement.
Return strict JSON only. Keep the same number of translated lines as the input lines.
Do not translate context lines unless they also appear in lines_to_translate."""


def _line_payload(line: SubtitleLine) -> dict[str, object]:
    return {
        "index": line.index,
        "start_ms": line.start,
        "end_ms": line.end,
        "style": line.style,
        "text": mask_ass_text(line.raw_text).text,
    }


def _knowledge_payload(chunk: TranslationChunk) -> dict[str, object]:
    context = chunk.prompt_context
    return {
        "series_title": context.series_title,
        "spoiler_mode": context.spoiler_mode,
        "summary": context.summary,
        "glossary_terms": [
            {
                "source": term.source,
                "target": term.target,
                "note": term.note,
                "protected": term.protected,
            }
            for term in context.terms
        ],
    }


def build_user_prompt(chunk: TranslationChunk) -> str:
    payload = {
        "knowledge": _knowledge_payload(chunk),
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
        "knowledge": _knowledge_payload(chunk),
        "context_before": [
            {"index": line.index, "text": mask_ass_text(line.raw_text).text}
            for line in chunk.context_before
        ],
        "lines_to_translate": [
            {"index": line.index, "text": mask_ass_text(line.raw_text).text}
            for line in chunk.lines
        ],
        "required_output": {
            "translations": [
                {"index": "integer from lines_to_translate", "translated_text": "Vietnamese ASS text"}
            ]
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
