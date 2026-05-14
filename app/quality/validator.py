from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pysubs2

from app.glossary.glossary import Glossary
from app.parser.ass_parser import ParsedSubtitle


ASS_TAG_RE = re.compile(r"\{\\[^{}]*\}")
ENGLISH_WORD_RE = re.compile(r"\b[a-zA-Z]{3,}\b")


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
) -> ValidationReport:
    return validate_translation_lines(parsed.lines, translations, glossary=glossary)


def validate_translation_lines(lines, translations: dict[int, str], glossary: Glossary | None = None) -> ValidationReport:
    report = ValidationReport()
    if len(translations) != len(lines):
        report.errors.append(f"Line count mismatch: {len(lines)} input lines, {len(translations)} translations.")

    for line in lines:
        translated = translations.get(line.index)
        if translated is None:
            report.errors.append(f"Missing translation for line {line.index}.")
            continue
        if line.raw_text.strip() and not translated.strip():
            report.errors.append(f"Empty translation for non-empty line {line.index}.")
        if translated.count("{") != translated.count("}"):
            report.errors.append(f"Unbalanced ASS override braces on line {line.index}.")

        original_tags = ASS_TAG_RE.findall(line.raw_text)
        translated_tags = ASS_TAG_RE.findall(translated)
        for tag in original_tags:
            if tag not in translated_tags:
                report.errors.append(f"Missing ASS tag on line {line.index}: {tag}")

        text_without_tags = ASS_TAG_RE.sub("", translated)
        words = ENGLISH_WORD_RE.findall(text_without_tags)
        if len(words) >= 5:
            report.warnings.append(f"Line {line.index} still appears mostly English.")
        if line.end > line.start:
            cps = len(text_without_tags) / ((line.end - line.start) / 1000)
            if cps > 25:
                report.warnings.append(f"Line {line.index} may be too long for its timing window.")
        if glossary is not None:
            _validate_glossary_terms(line.raw_text, translated, glossary, line.index, report)

    return report


def preserve_missing_ass_tags(lines, translations: dict[int, str]) -> dict[int, str]:
    fixed = dict(translations)
    for line in lines:
        translated = fixed.get(line.index)
        if translated is None:
            continue
        original_tags = ASS_TAG_RE.findall(line.raw_text)
        if not original_tags:
            continue
        translated_tags = ASS_TAG_RE.findall(translated)
        missing_tags = [tag for tag in original_tags if tag not in translated_tags]
        if missing_tags:
            fixed[line.index] = "".join(missing_tags) + translated
    return fixed


def _validate_glossary_terms(
    source_text: str,
    translated_text: str,
    glossary: Glossary,
    line_index: int,
    report: ValidationReport,
) -> None:
    source_lower = source_text.lower()
    translated_lower = translated_text.lower()
    for term in glossary.terms:
        if not term.protected:
            continue
        if term.source.lower() in source_lower and term.target.lower() not in translated_lower:
            report.warnings.append(f"Line {line_index} may have changed protected glossary term: {term.source}")
