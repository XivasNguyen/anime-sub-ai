from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx


@dataclass
class SeriesBible:
    title: str
    source_ids: dict[str, str] = field(default_factory=dict)
    titles: list[str] = field(default_factory=list)
    summary: str = ""
    character_names: list[str] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)
    honorific_notes: list[str] = field(default_factory=list)
    world_terms: list[str] = field(default_factory=list)
    spoiler_mode: str = "no_spoiler"
    warnings: list[str] = field(default_factory=list)

    @property
    def version(self) -> str:
        payload = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)
        import hashlib

        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "SeriesBible":
        return cls(
            title=str(data.get("title", "")),
            source_ids=dict(data.get("source_ids", {})),
            titles=list(data.get("titles", [])),
            summary=str(data.get("summary", "")),
            character_names=list(data.get("character_names", [])),
            relationships=list(data.get("relationships", [])),
            honorific_notes=list(data.get("honorific_notes", [])),
            world_terms=list(data.get("world_terms", [])),
            spoiler_mode=str(data.get("spoiler_mode", "no_spoiler")),
            warnings=list(data.get("warnings", [])),
        )


def infer_series_title(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"\[[^\]]+\]", " ", stem)
    stem = re.sub(r"\([^)]*\)", " ", stem)
    stem = re.sub(r"\bS\d+\b", " ", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\b\d{1,3}\b.*$", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" -_.")
    return stem or path.stem


def load_or_create_series_bible(
    title: str,
    cache_dir: Path,
    *,
    enable_web: bool = False,
    spoiler_mode: str = "no_spoiler",
) -> SeriesBible:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{_slug(title)}.{spoiler_mode}.series_bible.json"
    if path.exists():
        return SeriesBible.from_json(json.loads(path.read_text(encoding="utf-8")))

    bible = SeriesBible(
        title=title,
        titles=[title],
        spoiler_mode=spoiler_mode,
        honorific_notes=["Preserve common Japanese honorifics unless the glossary says otherwise."],
    )
    if enable_web:
        bible = _fetch_jikan_bible(title, spoiler_mode=spoiler_mode)
    path.write_text(json.dumps(bible.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")
    return bible


def _fetch_jikan_bible(title: str, *, spoiler_mode: str) -> SeriesBible:
    bible = SeriesBible(title=title, titles=[title], spoiler_mode=spoiler_mode)
    try:
        response = httpx.get(f"https://api.jikan.moe/v4/anime?q={quote(title)}&limit=1", timeout=15.0)
        response.raise_for_status()
        items = response.json().get("data", [])
        if not items:
            bible.warnings.append(f"No metadata match found for series title: {title}")
            return bible
        anime = items[0]
        mal_id = anime.get("mal_id")
        bible.source_ids["jikan_mal_id"] = str(mal_id)
        bible.title = str(anime.get("title") or title)
        bible.titles = _unique(
            [
                str(anime.get("title") or ""),
                str(anime.get("title_english") or ""),
                str(anime.get("title_japanese") or ""),
                *[
                    str(item.get("title") or "")
                    for item in anime.get("titles", [])
                    if isinstance(item, dict)
                ],
            ]
        )
        if spoiler_mode != "no_spoiler":
            bible.summary = _compact_summary(str(anime.get("synopsis") or ""))
        if mal_id:
            bible.character_names = _fetch_jikan_characters(mal_id)
    except Exception as exc:
        bible.warnings.append(f"Knowledge fetch failed: {exc}")
    return bible


def _fetch_jikan_characters(mal_id: int) -> list[str]:
    response = httpx.get(f"https://api.jikan.moe/v4/anime/{mal_id}/characters", timeout=15.0)
    response.raise_for_status()
    names: list[str] = []
    for item in response.json().get("data", [])[:24]:
        character = item.get("character", {})
        name = character.get("name")
        if isinstance(name, str) and name:
            names.append(name)
    return _unique(names)


def _compact_summary(summary: str, max_chars: int = 700) -> str:
    summary = re.sub(r"\s+", " ", summary).strip()
    if len(summary) <= max_chars:
        return summary
    return summary[:max_chars].rsplit(" ", 1)[0] + "..."


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "series"


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = value.strip()
        key = value.lower()
        if not value or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result
