from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

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
) -> ValidationReport:
    return validate_translation_lines(parsed.lines, translations, glossary=glossary)


def validate_translation_lines(lines, translations: dict[int, str], glossary: Glossary | None = None) -> ValidationReport:
    quality = build_quality_report(lines, translations, glossary)
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
        original_tags = ASS_TAG_RE.findall(line.raw_text)
        if not original_tags:
            continue
        translated_tags = ASS_TAG_RE.findall(translated)
        missing_tags = [tag for tag in original_tags if tag not in translated_tags]
        if missing_tags:
            fixed[line.index] = "".join(missing_tags) + translated
    return fixed


def _format_diagnostic(diagnostic) -> str:
    prefix = f"Line {diagnostic.line_index}: " if diagnostic.line_index else ""
    return f"{prefix}{diagnostic.message} [{diagnostic.code}]"
