from __future__ import annotations

import json

from app.parser.ass_parser import SubtitleLine
from app.translator.ass_mask import mask_ass_text
from app.translator.base import TranslationChunk


PROMPT_VERSION = "2026-05-16.dual-source-quality.v1"

SYSTEM_PROMPT = """You translate anime subtitles into natural Vietnamese for timed subtitle display.
Use English subtitles as the primary source and Japanese ASR as a secondary source to resolve ambiguity, missing nuance, names, and mismatch.
Preserve anime tone, honorifics, jokes, sarcasm, emotional nuance, names, and world terms.
Use conversational Vietnamese that sounds like real dialogue; avoid literal English word order and stiff textbook phrasing.
Prefer short readable subtitles. Keep reactions short. Keep stutters and comic timing when they matter.
Choose pronouns consistently from speaker/context; avoid random shifts between bạn/tôi, mày/ta, ngươi/ta.
Use provided knowledge and glossary terms when they are relevant to a line.
Protected glossary terms must remain consistent with their target values.
ASS override tags are replaced with placeholders like [[ASS_TAG_00]].
Preserve every placeholder exactly and keep its approximate placement.
Preserve subtitle line breaks as \\N. Never output raw newline characters inside translated_text.
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


def _audio_payload(chunk: TranslationChunk, line: SubtitleLine) -> dict[str, object]:
    audio = chunk.audio_context.get(line.index)
    if audio is None:
        return {
            "japanese_asr_text": "",
            "asr_confidence": 0.0,
            "asr_overlap_ms": 0,
            "asr_source": "none",
        }
    return {
        "japanese_asr_text": audio.japanese_text,
        "asr_confidence": round(audio.confidence, 3),
        "asr_overlap_ms": audio.overlap_ms,
        "asr_source": audio.source,
    }


def _translation_line_payload(chunk: TranslationChunk, line: SubtitleLine) -> dict[str, object]:
    payload = _line_payload(line)
    payload.update(
        {
            "english_text": payload.pop("text"),
            "speaker": line.name,
            **_audio_payload(chunk, line),
        }
    )
    return payload


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
        "lines_to_translate": [_translation_line_payload(chunk, line) for line in chunk.lines],
        "translation_style": {
            "target": "natural Vietnamese anime subtitles",
            "avoid": [
                "literal English word order",
                "raw English left untranslated unless it is a name/term",
                "raw newline characters",
                "overlong lines that are hard to read in the timing window",
            ],
            "line_break": "Use \\N, not raw newlines.",
        },
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
            {
                "index": line.index,
                "english_text": mask_ass_text(line.raw_text).text,
                "speaker": line.name,
                "style": line.style,
                **_audio_payload(chunk, line),
            }
            for line in chunk.lines
        ],
        "style": "Natural concise Vietnamese anime subtitles. Use Japanese ASR only as secondary evidence. Preserve [[ASS_TAG_00]] placeholders and \\N line breaks.",
        "required_output": {
            "translations": [
                {"index": "integer from lines_to_translate", "translated_text": "Vietnamese ASS text"}
            ]
        },
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
