from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.knowledge.series_bible import SeriesBible
from app.parser.ass_parser import SubtitleLine
from app.translator.base import PromptTerm


HONORIFICS = {
    "senpai",
    "sensei",
    "sama",
    "san",
    "chan",
    "kun",
    "onii-chan",
    "onee-sama",
}
STOPWORDS = {
    "a",
    "all",
    "am",
    "an",
    "and",
    "are",
    "as",
    "at",
    "but",
    "by",
    "come",
    "could",
    "do",
    "does",
    "episode",
    "first",
    "for",
    "from",
    "give",
    "good",
    "great",
    "have",
    "he",
    "here",
    "hey",
    "i",
    "if",
    "in",
    "is",
    "it",
    "keep",
    "later",
    "let",
    "like",
    "man",
    "no",
    "not",
    "of",
    "okay",
    "or",
    "right",
    "see",
    "shall",
    "she",
    "so",
    "that",
    "the",
    "then",
    "this",
    "to",
    "tv",
    "we",
    "well",
    "what",
    "wha",
    "which",
    "why",
    "work",
    "yeah",
    "you",
    "you're",
    "your",
}
CAPITALIZED_RE = re.compile(r"\b[A-Z][A-Za-z][A-Za-z'-]*(?:\s+[A-Z][A-Za-z][A-Za-z'-]*){0,3}\b")


@dataclass(frozen=True)
class GlossaryTerm:
    source: str
    target: str
    note: str = ""
    protected: bool = True

    def to_prompt_term(self) -> PromptTerm:
        return PromptTerm(
            source=self.source,
            target=self.target,
            note=self.note,
            protected=self.protected,
        )


@dataclass
class Glossary:
    terms: list[GlossaryTerm] = field(default_factory=list)

    @property
    def version(self) -> str:
        digest = hashlib.sha256()
        for term in sorted(self.terms, key=lambda item: item.source.lower()):
            digest.update(f"{term.source}\0{term.target}\0{term.note}\0{term.protected}".encode("utf-8"))
        return digest.hexdigest()[:16] if self.terms else "none"

    def relevant_terms(self, lines: list[SubtitleLine], limit: int = 12) -> list[PromptTerm]:
        text = "\n".join(line.raw_text for line in lines).lower()
        matched: list[GlossaryTerm] = []
        for term in self.terms:
            if term.source.lower() in text:
                matched.append(term)
        if len(matched) < limit:
            existing = {term.source.lower() for term in matched}
            for term in self.terms:
                if term.source.lower() not in existing:
                    matched.append(term)
                if len(matched) >= limit:
                    break
        return [term.to_prompt_term() for term in matched[:limit]]

    def protected_sources(self) -> set[str]:
        return {term.source for term in self.terms if term.protected}


def build_glossary(lines: list[SubtitleLine], bible: SeriesBible | None = None) -> Glossary:
    terms: dict[str, GlossaryTerm] = {}
    if bible is not None:
        for name in bible.character_names:
            if name:
                terms[name.lower()] = GlossaryTerm(source=name, target=name, note="Character name", protected=True)
        for term in bible.world_terms:
            if term:
                terms[term.lower()] = GlossaryTerm(source=term, target=term, note="Series term", protected=True)

    counts: dict[str, int] = {}
    suffix_terms: set[str] = set()
    name_field_terms: set[str] = set()
    for line in lines:
        scan_text = line.text.replace("\\N", " ")
        if line.name and line.name.strip() and line.name.strip().lower() not in STOPWORDS:
            name_field_terms.add(line.name.strip())
            counts[line.name.strip()] = counts.get(line.name.strip(), 0) + 2
        for honorific in HONORIFICS:
            if honorific in line.raw_text.lower():
                counts[honorific] = counts.get(honorific, 0) + 1
        for match in CAPITALIZED_RE.findall(scan_text):
            match = match.strip()
            key = match.lower().strip("'")
            if key in STOPWORDS or key in {"english", "default"}:
                continue
            if len(match) <= 2:
                continue
            counts[match] = counts.get(match, 0) + 1
            if "-" in match:
                base, suffix = match.rsplit("-", 1)
                if suffix.lower().strip("'s") in HONORIFICS and base.lower() not in STOPWORDS:
                    counts[base] = counts.get(base, 0) + 1
                    suffix_terms.add(base)
                    suffix_terms.add(match)

    for source, count in counts.items():
        source_key = source.lower()
        if count < 2 and source_key not in HONORIFICS:
            continue
        if source_key not in HONORIFICS and " " not in source and "-" not in source and count < 2:
            continue
        protected = (
            source_key in HONORIFICS
            or source in suffix_terms
            or source in name_field_terms
            or (count >= 3 and source_key not in STOPWORDS and _looks_like_name(source))
        )
        terms.setdefault(
            source_key,
            GlossaryTerm(
                source=source,
                target=source,
                note=f"Auto-detected {count}x",
                protected=protected,
            ),
        )

    return Glossary(terms=sorted(terms.values(), key=lambda item: item.source.lower()))


def _looks_like_name(value: str) -> bool:
    return bool(value and value[0].isupper() and value.lower() not in STOPWORDS and len(value) > 2)


def load_manual_glossary(path: Path) -> Glossary:
    if not path.exists():
        return Glossary()
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_terms = data.get("terms", data) if isinstance(data, dict) else data
    terms: list[GlossaryTerm] = []

    if isinstance(raw_terms, dict):
        for source, target in raw_terms.items():
            terms.append(GlossaryTerm(source=str(source), target=str(target), note="Manual glossary"))
    elif isinstance(raw_terms, list):
        for item in raw_terms:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source", "")).strip()
            if not source:
                continue
            terms.append(
                GlossaryTerm(
                    source=source,
                    target=str(item.get("target", source)).strip() or source,
                    note=str(item.get("note", "Manual glossary")),
                    protected=bool(item.get("protected", True)),
                )
            )
    return Glossary(terms=terms)


def merge_glossaries(*glossaries: Glossary) -> Glossary:
    merged: dict[str, GlossaryTerm] = {}
    for glossary in reversed(glossaries):
        for term in glossary.terms:
            merged[term.source.lower()] = term
    return Glossary(terms=sorted(merged.values(), key=lambda item: item.source.lower()))
