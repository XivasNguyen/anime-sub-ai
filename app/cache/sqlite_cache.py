from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.parser.ass_parser import SubtitleLine
from app.translator.base import TranslationChunk, TranslationResult


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    writes: int = 0


class TranslationCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.stats = CacheStats()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.connection.close()

    def get_chunk(self, key: str) -> list[TranslationResult] | None:
        row = self.connection.execute("SELECT payload FROM translation_cache WHERE cache_key = ?", (key,)).fetchone()
        if row is None:
            self.stats.misses += 1
            return None
        self.stats.hits += 1
        payload = json.loads(row["payload"])
        return [
            TranslationResult(index=int(item["index"]), translated_text=str(item["translated_text"]))
            for item in payload["translations"]
        ]

    def put_chunk(self, key: str, results: list[TranslationResult], metadata: dict[str, Any]) -> None:
        payload = {
            "translations": [{"index": result.index, "translated_text": result.translated_text} for result in results],
            "metadata": metadata,
        }
        self.connection.execute(
            """
            INSERT INTO translation_cache(cache_key, payload, metadata_json, updated_at)
            VALUES(?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            ON CONFLICT(cache_key) DO UPDATE SET
              payload = excluded.payload,
              metadata_json = excluded.metadata_json,
              updated_at = excluded.updated_at
            """,
            (key, json.dumps(payload, ensure_ascii=False), json.dumps(metadata, ensure_ascii=False)),
        )
        self.connection.commit()
        self.stats.writes += 1

    def _init_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS translation_cache(
              cache_key TEXT PRIMARY KEY,
              payload TEXT NOT NULL,
              metadata_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()


def chunk_cache_key(
    chunk: TranslationChunk,
    *,
    provider: str,
    model: str,
    prompt_version: str,
    glossary_version: str,
    ass_version: str,
) -> str:
    payload = {
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "glossary_version": glossary_version,
        "ass_version": ass_version,
        "lines": [_line_payload(line) for line in chunk.lines],
        "context": [_line_payload(line) for line in chunk.context_before],
        "prompt_context": {
            "series_title": chunk.prompt_context.series_title,
            "summary": chunk.prompt_context.summary,
            "spoiler_mode": chunk.prompt_context.spoiler_mode,
            "terms": [term.__dict__ for term in chunk.prompt_context.terms],
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _line_payload(line: SubtitleLine) -> dict[str, Any]:
    return {
        "index": line.index,
        "start": line.start,
        "end": line.end,
        "style": line.style,
        "raw_text": line.raw_text,
    }
