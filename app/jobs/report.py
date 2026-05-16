from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TranslationReport:
    job_id: str
    provider: str
    model: str
    input_video: str
    source_subtitle: str = ""
    output_subtitle: str = ""
    output_mkv: str = ""
    total_lines: int = 0
    translated_lines: int = 0
    elapsed_seconds: float = 0.0
    lines_per_second: float = 0.0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_writes: int = 0
    chunk_count: int = 0
    completed_chunks: int = 0
    retry_splits: int = 0
    chunk_timings: list[float] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    knowledge: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
