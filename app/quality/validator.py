from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pysubs2

from app.glossary.glossary import Glossary
from app.parser.ass_parser import ParsedSubtitle
from app.quality.report import build_quality_report


ASS_TAG_RE = re.compile(r"\{\\[^{}]*\}")


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def raise_for_errors(self) -> None:
        if self.errors:
            raise ValueError("Validation failed:\n" + "\n".join(f"- {error}" for error in self.errors))


def validate_ass_file(path: Path) -> ValidationReport:
    report = ValidationReport()
    try:
        pysubs2.load(str(path), encoding="utf-8")
    except Exception as exc:
        report.errors.append(f"ASS file cannot be loaded: {exc}")
    return report


def validate_translations(
    parsed: ParsedSubtitle,
    translations: dict[int, str],
    glossary: Glossary | None = None,
    audio_context: dict[int, Any] | None = None,
) -> ValidationReport:
    return validate_translation_lines(parsed.lines, translations, glossary=glossary, audio_context=audio_context)


def validate_translation_lines(
    lines,
    translations: dict[int, str],
    glossary: Glossary | None = None,
    audio_context: dict[int, Any] | None = None,
) -> ValidationReport:
    quality = build_quality_report(lines, translations, glossary, audio_context=audio_context)
    report = ValidationReport()
    report.errors.extend(_format_diagnostic(item) for item in quality.errors)
    report.warnings.extend(_format_diagnostic(item) for item in quality.warnings)
    return report


def preserve_missing_ass_tags(lines, translations: dict[int, str]) -> dict[int, str]:
    fixed = dict(translations)
    for line in lines:
        translated = fixed.get(line.index)
        if translated is None:
            continue
        translated = normalize_subtitle_line_breaks(line.raw_text, translated)
        original_tags = ASS_TAG_RE.findall(line.raw_text)
        if original_tags:
            translated_tags = ASS_TAG_RE.findall(translated)
            missing_tags = [tag for tag in original_tags if tag not in translated_tags]
            if missing_tags:
                translated = "".join(missing_tags) + translated
        fixed[line.index] = translated
    return fixed


def normalize_subtitle_line_breaks(source_text: str, translated_text: str) -> str:
    normalized = translated_text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\\n", "\\N")
    if "\n" in normalized:
        normalized = normalized.replace("\n", "\\N")
    if "\\N" not in source_text or "\\N" in normalized:
        return normalized

    visible = ASS_TAG_RE.sub("", normalized)
    if len(visible) < 28:
        return normalized
    return _insert_balanced_line_break(normalized)


def _insert_balanced_line_break(text: str) -> str:
    break_candidates = [index for index, char in enumerate(text) if char == " "]
    if not break_candidates:
        return text
    midpoint = len(text) / 2
    best = min(break_candidates, key=lambda index: abs(index - midpoint))
    return f"{text[:best]}\\N{text[best + 1:]}"


def _format_diagnostic(diagnostic) -> str:
    prefix = f"Line {diagnostic.line_index}: " if diagnostic.line_index else ""
    return f"{prefix}{diagnostic.message} [{diagnostic.code}]"
