from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.glossary.glossary import Glossary
from app.parser.ass_parser import SubtitleLine


ASS_TAG_RE = re.compile(r"\{\\[^{}]*\}")
ENGLISH_WORD_RE = re.compile(r"\b[a-zA-Z]{3,}\b")
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
PLACEHOLDER_RE = re.compile(r"\[\[ASS_TAG_\d{2}\]\]")
SHORT_UNTRANSLATED_RE = re.compile(
    r"^(wait|stop|huh|hey|what|where are you|one after another|copycat|sniff|senpai)[!?.\s-]*$",
    re.IGNORECASE,
)
LITERAL_VI_PATTERNS = (
    "điều này",
    "với điều này",
    "như thế nào",
    "một quỷ",
    "tôi sẽ cho bạn thấy",
    "bởi vì cô ấy",
)


@dataclass(frozen=True)
class LineDiagnostic:
    line_index: int
    severity: str
    code: str
    message: str
    source_text: str = ""
    translated_text: str = ""

    def to_json(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class QualityReport:
    diagnostics: list[LineDiagnostic] = field(default_factory=list)

    @property
    def errors(self) -> list[LineDiagnostic]:
        return [item for item in self.diagnostics if item.severity == "error"]

    @property
    def warnings(self) -> list[LineDiagnostic]:
        return [item for item in self.diagnostics if item.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def warning_line_indexes(self) -> set[int]:
        return {item.line_index for item in self.warnings if item.line_index > 0}

    def to_json(self) -> list[dict[str, object]]:
        return [item.to_json() for item in self.diagnostics]


def build_quality_report(
    lines: list[SubtitleLine],
    translations: dict[int, str],
    glossary: Glossary | None = None,
    audio_context: dict[int, Any] | None = None,
) -> QualityReport:
    report = QualityReport()
    translated_values: dict[str, list[int]] = {}

    if len(translations) != len(lines):
        report.diagnostics.append(
            LineDiagnostic(
                line_index=0,
                severity="error",
                code="line_count_mismatch",
                message=f"Line count mismatch: {len(lines)} input lines, {len(translations)} translations.",
            )
        )

    for line in lines:
        translated = translations.get(line.index)
        if translated is None:
            _add(report, line, "", "error", "missing_translation", f"Missing translation for line {line.index}.")
            continue

        normalized_translation = _normalize_visible_text(translated)
        if normalized_translation:
            translated_values.setdefault(normalized_translation, []).append(line.index)

        if line.raw_text.strip() and not translated.strip():
            _add(report, line, translated, "error", "empty_translation", "Empty translation for non-empty source line.")
        if translated.count("{") != translated.count("}"):
            _add(report, line, translated, "error", "unbalanced_ass_braces", "Unbalanced ASS override braces.")
        if PLACEHOLDER_RE.search(translated):
            _add(report, line, translated, "error", "placeholder_leak", "ASS placeholder leaked into final translation.")
        if "\n" in translated or "\\n" in translated:
            _add(report, line, translated, "warning", "linebreak_normalized", "Line contains raw newline syntax; use ASS \\N.")

        original_tags = ASS_TAG_RE.findall(line.raw_text)
        translated_tags = ASS_TAG_RE.findall(translated)
        for tag in original_tags:
            if tag not in translated_tags:
                _add(report, line, translated, "error", "missing_ass_tag", f"Missing ASS tag: {tag}")

        if "\\N" in line.raw_text and "\\N" not in translated:
            _add(report, line, translated, "warning", "missing_line_break", "Original line break \\N was removed.")

        text_without_tags = ASS_TAG_RE.sub("", translated)
        words = ENGLISH_WORD_RE.findall(text_without_tags)
        if len(words) >= 5:
            _add(report, line, translated, "warning", "mostly_english", "Line still appears mostly English.")
        elif SHORT_UNTRANSLATED_RE.match(text_without_tags.strip()):
            _add(report, line, translated, "warning", "untranslated_short_phrase", "Short phrase appears untranslated.")
        if CJK_RE.search(text_without_tags):
            _add(report, line, translated, "warning", "cjk_leakage", "Line contains Chinese/Japanese characters.")
        lower_translation = text_without_tags.lower()
        if any(pattern in lower_translation for pattern in LITERAL_VI_PATTERNS):
            _add(report, line, translated, "warning", "too_literal", "Line contains a phrase that often signals literal translation.")
        if _has_pronoun_shift(text_without_tags):
            _add(report, line, translated, "warning", "bad_pronoun_shift", "Line mixes multiple Vietnamese pronoun registers.")
        if line.end > line.start:
            cps = len(text_without_tags.replace("\\N", "")) / ((line.end - line.start) / 1000)
            if cps > 25:
                _add(report, line, translated, "warning", "high_cps", "Line may be too long for its timing window.")
        if audio_context is not None:
            _validate_audio_context(line, translated, audio_context, report)
        if glossary is not None:
            _validate_glossary_terms(line, translated, glossary, report)

    for normalized, indexes in translated_values.items():
        if len(indexes) > 1 and len(normalized) > 12:
            for index in indexes:
                line = next((item for item in lines if item.index == index), None)
                if line is not None:
                    _add(
                        report,
                        line,
                        translations[index],
                        "warning",
                        "duplicate_translation",
                        f"Same translated text also appears on lines: {indexes}",
                    )

    return report


def _add(
    report: QualityReport,
    line: SubtitleLine,
    translated: str,
    severity: str,
    code: str,
    message: str,
) -> None:
    report.diagnostics.append(
        LineDiagnostic(
            line_index=line.index,
            severity=severity,
            code=code,
            message=message,
            source_text=line.raw_text,
            translated_text=translated,
        )
    )


def _validate_glossary_terms(
    line: SubtitleLine,
    translated_text: str,
    glossary: Glossary,
    report: QualityReport,
) -> None:
    source_lower = line.raw_text.lower()
    translated_lower = translated_text.lower()
    for term in glossary.terms:
        if not term.protected:
            continue
        if term.source.lower() in source_lower and term.target.lower() not in translated_lower:
            _add(
                report,
                line,
                translated_text,
                "warning",
                "protected_glossary_changed",
                f"Protected glossary term may have changed: {term.source}",
            )


def _validate_audio_context(
    line: SubtitleLine,
    translated_text: str,
    audio_context: dict[int, Any],
    report: QualityReport,
) -> None:
    context = audio_context.get(line.index)
    if context is None:
        return
    japanese_text = str(getattr(context, "japanese_text", "") or "").strip()
    confidence = float(getattr(context, "confidence", 0.0) or 0.0)
    if japanese_text and confidence < 0.35:
        _add(
            report,
            line,
            translated_text,
            "warning",
            "asr_sub_mismatch",
            "Japanese ASR is low-confidence for this subtitle line; review dual-source alignment.",
        )


def _has_pronoun_shift(text: str) -> bool:
    lowered = text.lower()
    rough = {"bạn", "tôi"}
    casual = {"mày", "tao"}
    archaic = {"ngươi", "ta"}
    buckets = sum(1 for bucket in (rough, casual, archaic) if any(word in lowered for word in bucket))
    return buckets >= 2


def _normalize_visible_text(text: str) -> str:
    without_tags = ASS_TAG_RE.sub("", text)
    return re.sub(r"\s+", " ", without_tags.replace("\\N", " ")).strip().lower()
