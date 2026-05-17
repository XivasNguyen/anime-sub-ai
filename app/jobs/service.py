from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.audio.dual_source import DualSourceReport, build_dual_source_context
from app.cache.sqlite_cache import TranslationCache
from app.config.settings import Settings
from app.extractor.subtitle_extractor import extract_subtitle
from app.formatter.ass_formatter import rebuild_ass
from app.glossary.glossary import Glossary, build_glossary, load_manual_glossary, merge_glossaries
from app.jobs.report import TranslationReport
from app.knowledge.series_bible import SeriesBible, infer_series_title, load_or_create_series_bible
from app.muxer.mkv_muxer import mux_softsub
from app.parser.ass_parser import parse_ass
from app.quality.report import build_quality_report
from app.quality.validator import (
    preserve_missing_ass_tags,
    validate_ass_file,
    validate_translation_lines,
    validate_translations,
)
from app.translator.base import PromptContext
from app.translator.factory import create_translator
from app.translator.health import check_provider_health, require_provider_available
from app.translator.pipeline import PipelineStats, translate_lines


@dataclass
class TranslationJobOptions:
    video: Path
    provider_name: str
    model: str | None = None
    batch_size: int | None = None
    max_concurrency: int | None = None
    start_line: int = 1
    limit_lines: int | None = None
    skip_mux: bool = False
    set_default_sub: bool | None = None
    dry_run: bool = False
    series_title: str | None = None
    knowledge_enabled: bool | None = None
    knowledge_web: bool | None = None
    spoiler_mode: str | None = None
    resume: bool = True
    force_retranslate: bool = False
    cache_path: Path | None = None
    repair_warnings: bool = False
    glossary_path: Path | None = None
    dual_source: bool | None = None
    asr_model: str | None = None
    asr_device: str | None = None
    quality_preset: str | None = None
    repair_mode: str | None = None


@dataclass
class TranslationJobResult:
    job_id: str
    subtitle_path: Path | None
    mkv_path: Path | None
    report_path: Path | None
    report: TranslationReport


def create_job(settings: Settings, options: TranslationJobOptions) -> str:
    job_id = uuid.uuid4().hex[:12]
    _write_job_state(settings, job_id, "created", {"options": _jsonable_options(options)})
    return job_id


def start_job(settings: Settings, options: TranslationJobOptions, job_id: str | None = None) -> TranslationJobResult:
    job_id = job_id or create_job(settings, options)
    _write_job_state(settings, job_id, "running", {"phase": "extract"})

    provider_name = options.provider_name.lower()
    model = options.model or _default_model(settings, provider_name)
    output_dir = settings.output.directory
    temp_dir = settings.output.temp_directory
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    warnings: list[str] = []
    errors: list[str] = []
    cache: TranslationCache | None = None
    stats = PipelineStats()
    dual_source_report = DualSourceReport()
    repair_count = 0
    source_subtitle = ""
    output_subtitle: Path | None = None
    output_mkv: Path | None = None

    try:
        _validate_options(options)
        if not options.dry_run:
            _write_job_state(settings, job_id, "running", {"phase": "provider_check"})
            health = asyncio.run(check_provider_health(settings, provider_name, model=model))
            if not health.available:
                _write_job_state(
                    settings,
                    job_id,
                    "failed",
                    {"phase": "provider_check", "error": health.message, "provider_health": health.to_json()},
                )
            require_provider_available(health)

        _write_job_state(settings, job_id, "running", {"phase": "extract"})
        source_path = extract_subtitle(options.video, temp_dir)
        source_subtitle = str(source_path)
        parsed = parse_ass(source_path)
        _write_job_state(settings, job_id, "running", {"phase": "parse", "total_lines": len(parsed.lines)})

        if options.dry_run:
            report = _build_report(
                job_id,
                provider_name,
                model,
                options,
                settings,
                source_subtitle=source_subtitle,
                warnings=warnings,
                errors=errors,
                elapsed=time.perf_counter() - started,
                stats=stats,
                cache=cache,
                translated_lines=0,
                total_lines=len(parsed.lines),
                glossary=None,
                bible=None,
            )
            report_path = output_dir / f"{options.video.stem}.{job_id}.report.json"
            report.write(report_path)
            _write_job_state(settings, job_id, "completed", {"phase": "dry_run", "report": str(report_path)})
            return TranslationJobResult(job_id, None, None, report_path, report)

        selected_lines = parsed.lines[options.start_line - 1 :]
        if options.limit_lines is not None:
            selected_lines = selected_lines[: options.limit_lines]
        if not selected_lines:
            raise ValueError("Selected subtitle line range is empty.")
        if options.limit_lines is not None and not options.skip_mux:
            raise ValueError("Partial translation requires skip_mux to avoid creating a mixed full-episode MKV.")

        _write_job_state(settings, job_id, "running", {"phase": "research"})
        bible = _load_bible(settings, options)
        warnings.extend(bible.warnings)
        auto_glossary = build_glossary(parsed.lines, bible)
        manual_glossary = load_manual_glossary(options.glossary_path or settings.glossary.path)
        glossary = merge_glossaries(manual_glossary, auto_glossary)

        _write_job_state(settings, job_id, "running", {"phase": "audio_asr"})
        audio_context, dual_source_report = build_dual_source_context(
            options.video,
            selected_lines,
            temp_dir,
            enabled=settings.asr.dual_source if options.dual_source is None else options.dual_source,
            model=options.asr_model or settings.asr.model,
            device=options.asr_device or settings.asr.device,
            compute_type=settings.asr.compute_type or None,
        )
        warnings.extend(dual_source_report.warnings)

        cache_path = options.cache_path or settings.cache.path
        if settings.cache.enabled:
            cache = TranslationCache(cache_path)

        _write_job_state(settings, job_id, "running", {"phase": "translate", "selected_lines": len(selected_lines)})
        translator = create_translator(settings, provider_name=provider_name, model=model)
        chunk_size = _effective_chunk_size(settings, options)
        max_concurrency = options.max_concurrency or settings.translation.max_concurrency
        translations = asyncio.run(
            translate_lines(
                selected_lines,
                translator,
                chunk_size=chunk_size,
                overlap_lines=settings.translation.overlap_lines,
                max_concurrency=max_concurrency,
                prompt_context_builder=lambda lines: _build_prompt_context(bible, glossary, lines),
                audio_context=audio_context,
                cache=cache,
                provider_name=provider_name,
                model=model,
                force_retranslate=options.force_retranslate or not options.resume,
                stats=stats,
                progress_callback=lambda payload: _write_job_state(
                    settings,
                    job_id,
                    "running",
                    {
                        "phase": "translate",
                        "selected_lines": len(selected_lines),
                        "translated_lines": payload.get("completed_chunks", 0)
                        * chunk_size,
                        "can_cancel": True,
                        **payload,
                    },
                ),
            )
        )
        translations = preserve_missing_ass_tags(selected_lines, translations)

        _write_job_state(settings, job_id, "running", {"phase": "validate"})
        quality = build_quality_report(selected_lines, translations, glossary=glossary, audio_context=audio_context)
        repair_mode = options.repair_mode or settings.translation.repair_mode
        if options.repair_warnings:
            repair_mode = "warnings"
        repair_indexes = _repair_line_indexes(quality, repair_mode)
        if repair_indexes:
            _write_job_state(settings, job_id, "running", {"phase": "repair", "warning_lines": sorted(repair_indexes)})
            repair_lines = [line for line in selected_lines if line.index in repair_indexes]
            repaired = asyncio.run(
                translate_lines(
                    repair_lines,
                    create_translator(settings, provider_name=provider_name, model=model),
                    chunk_size=1,
                    overlap_lines=0,
                    max_concurrency=1,
                    prompt_context_builder=lambda lines: _build_prompt_context(bible, glossary, lines),
                    audio_context=audio_context,
                    cache=cache,
                    provider_name=provider_name,
                    model=model,
                    force_retranslate=True,
                    stats=stats,
                )
            )
            translations.update(preserve_missing_ass_tags(repair_lines, repaired))
            repair_count = len(repair_lines)
            quality = build_quality_report(selected_lines, translations, glossary=glossary, audio_context=audio_context)

        validation = validate_translation_lines(selected_lines, translations, glossary=glossary, audio_context=audio_context)
        warnings.extend(validation.warnings)
        validation.raise_for_errors()

        if options.limit_lines is None and options.start_line == 1:
            output_subtitle = output_dir / f"{options.video.stem}.vi.ass"
        else:
            end_line = selected_lines[-1].index
            output_subtitle = output_dir / f"{options.video.stem}.vi.lines-{selected_lines[0].index}-{end_line}.ass"
        rebuild_ass(parsed, translations, output_subtitle)
        validate_ass_file(output_subtitle).raise_for_errors()

        if not options.skip_mux:
            validate_translations(parsed, translations, glossary=glossary, audio_context=audio_context).raise_for_errors()
            output_mkv = output_dir / f"{options.video.stem}.vi.mkv"
            _write_job_state(settings, job_id, "running", {"phase": "mux"})
            mux_softsub(
                options.video,
                output_subtitle,
                output_mkv,
                language=settings.mux.subtitle_language,
                track_name=settings.mux.subtitle_track_name,
                set_default=settings.mux.set_default_subtitle if options.set_default_sub is None else options.set_default_sub,
            )

        elapsed = time.perf_counter() - started
        report = _build_report(
            job_id,
            provider_name,
            model,
            options,
            settings,
            source_subtitle=source_subtitle,
            output_subtitle=str(output_subtitle or ""),
            output_mkv=str(output_mkv or ""),
            warnings=warnings,
            errors=errors,
            elapsed=elapsed,
            stats=stats,
            cache=cache,
            translated_lines=len(selected_lines),
            total_lines=len(parsed.lines),
            glossary=glossary,
            bible=bible,
            diagnostics=quality.to_json(),
            dual_source=dual_source_report.to_json(),
            quality_gate=_quality_gate(quality, repair_count),
        )
        report_path = (output_subtitle or output_dir / f"{options.video.stem}.vi.ass").with_suffix(".report.json")
        report.write(report_path)
        _write_job_state(settings, job_id, "completed", {"phase": "done", "report": str(report_path)})
        return TranslationJobResult(job_id, output_subtitle, output_mkv, report_path, report)
    except Exception as exc:
        errors.append(str(exc))
        elapsed = time.perf_counter() - started
        report = _build_report(
            job_id,
            provider_name,
            model,
            options,
            settings,
            source_subtitle=source_subtitle,
            output_subtitle=str(output_subtitle or ""),
            output_mkv=str(output_mkv or ""),
            warnings=warnings,
            errors=errors,
            elapsed=elapsed,
            stats=stats,
            cache=cache,
            translated_lines=0,
            total_lines=0,
            glossary=None,
            bible=None,
            diagnostics=[],
            dual_source=dual_source_report.to_json(),
            quality_gate={"repair_count": repair_count},
        )
        report_path = settings.output.directory / f"{options.video.stem}.{job_id}.failed.report.json"
        report.write(report_path)
        _write_job_state(settings, job_id, "failed", {"phase": "failed", "error": str(exc), "report": str(report_path)})
        raise
    finally:
        if cache is not None:
            cache.close()


def cancel_job(settings: Settings, job_id: str) -> None:
    _write_job_state(settings, job_id, "cancelled", {"phase": "cancelled"})


def get_progress(settings: Settings, job_id: str) -> dict[str, Any]:
    with _job_connection(settings) as connection:
        row = connection.execute("SELECT * FROM translation_jobs WHERE job_id = ?", (job_id,)).fetchone()
    if row is None:
        return {}
    return {"job_id": row["job_id"], "status": row["status"], "payload": json.loads(row["payload_json"])}


def list_outputs(settings: Settings) -> list[Path]:
    if not settings.output.directory.exists():
        return []
    return sorted(settings.output.directory.glob("*.vi.*"))


def _load_bible(settings: Settings, options: TranslationJobOptions) -> SeriesBible:
    title = options.series_title or infer_series_title(options.video)
    enabled = settings.knowledge.enabled if options.knowledge_enabled is None else options.knowledge_enabled
    enable_web = settings.knowledge.enable_web if options.knowledge_web is None else options.knowledge_web
    spoiler_mode = options.spoiler_mode or settings.knowledge.spoiler_mode
    return load_or_create_series_bible(
        title,
        settings.knowledge.cache_directory,
        enable_web=enabled and enable_web,
        spoiler_mode=spoiler_mode,
    )


def _validate_options(options: TranslationJobOptions) -> None:
    if not options.video.exists():
        raise ValueError(f"Input video does not exist: {options.video}")
    if not options.video.is_file():
        raise ValueError(f"Input video is not a file: {options.video}")
    if options.video.suffix.lower() != ".mkv":
        raise ValueError("Input video must be an .mkv file.")
    if options.batch_size is not None and options.batch_size < 1:
        raise ValueError("Batch size must be greater than 0.")
    if options.max_concurrency is not None and options.max_concurrency < 1:
        raise ValueError("Concurrency must be greater than 0.")
    if options.start_line < 1:
        raise ValueError("Start line must be greater than 0.")
    if options.limit_lines is not None and options.limit_lines < 1:
        raise ValueError("Limit lines must be greater than 0.")
    if options.repair_mode is not None and options.repair_mode not in {"none", "warnings", "production"}:
        raise ValueError("Repair mode must be one of: none, warnings, production.")
    if options.quality_preset is not None and options.quality_preset not in {"fast", "balanced", "production"}:
        raise ValueError("Quality preset must be one of: fast, balanced, production.")
    if options.asr_model is not None and options.asr_model not in {"turbo", "small", "medium", "large-v3"}:
        raise ValueError("ASR model must be one of: turbo, small, medium, large-v3.")
    if options.asr_device is not None and options.asr_device not in {"cuda", "cpu"}:
        raise ValueError("ASR device must be cuda or cpu.")


def _build_prompt_context(bible: SeriesBible, glossary: Glossary, selected_lines) -> PromptContext:
    terms = glossary.relevant_terms(selected_lines, limit=14)
    summary = bible.summary if bible.spoiler_mode != "no_spoiler" else ""
    return PromptContext(
        series_title=bible.title,
        summary=summary,
        spoiler_mode=bible.spoiler_mode,
        terms=terms,
        version=f"{bible.version}.{glossary.version}",
    )


def _build_report(
    job_id: str,
    provider: str,
    model: str,
    options: TranslationJobOptions,
    settings: Settings,
    *,
    source_subtitle: str = "",
    output_subtitle: str = "",
    output_mkv: str = "",
    warnings: list[str],
    errors: list[str],
    elapsed: float,
    stats: PipelineStats,
    cache: TranslationCache | None,
    translated_lines: int,
    total_lines: int,
    glossary: Glossary | None,
    bible: SeriesBible | None,
    diagnostics: list[dict[str, Any]] | None = None,
    dual_source: dict[str, Any] | None = None,
    quality_gate: dict[str, Any] | None = None,
) -> TranslationReport:
    cache_stats = cache.stats if cache is not None else None
    return TranslationReport(
        job_id=job_id,
        provider=provider,
        model=model,
        input_video=str(options.video),
        source_subtitle=source_subtitle,
        output_subtitle=output_subtitle,
        output_mkv=output_mkv,
        total_lines=total_lines,
        translated_lines=translated_lines,
        elapsed_seconds=elapsed,
        lines_per_second=(translated_lines / elapsed) if elapsed > 0 else 0.0,
        cache_hits=cache_stats.hits if cache_stats else 0,
        cache_misses=cache_stats.misses if cache_stats else 0,
        cache_writes=cache_stats.writes if cache_stats else 0,
        chunk_count=stats.chunk_count,
        completed_chunks=stats.completed_chunks,
        retry_splits=stats.retry_splits,
        chunk_timings=stats.chunk_timings,
        diagnostics=diagnostics or [],
        dual_source=dual_source or {},
        quality_gate=quality_gate or {},
        warnings=warnings,
        errors=errors,
        knowledge={
            "series_title": bible.title if bible else "",
            "spoiler_mode": bible.spoiler_mode if bible else "",
            "source_ids": bible.source_ids if bible else {},
            "glossary_version": glossary.version if glossary else "none",
            "glossary_terms": len(glossary.terms) if glossary else 0,
        },
        settings={
            "batch_size": options.batch_size,
            "max_concurrency": options.max_concurrency,
            "effective_batch_size": _effective_chunk_size(settings, options),
            "start_line": options.start_line,
            "limit_lines": options.limit_lines,
            "skip_mux": options.skip_mux,
            "resume": options.resume,
            "force_retranslate": options.force_retranslate,
            "repair_warnings": options.repair_warnings,
            "repair_mode": options.repair_mode,
            "quality_preset": options.quality_preset,
            "dual_source": options.dual_source,
            "asr_model": options.asr_model,
            "asr_device": options.asr_device,
        },
    )


def _repair_line_indexes(quality, repair_mode: str) -> set[int]:
    mode = (repair_mode or "none").lower()
    if mode == "none":
        return set()
    if mode == "warnings":
        return quality.warning_line_indexes()
    if mode != "production":
        return set()
    repairable_codes = {
        "cjk_leakage",
        "linebreak_normalized",
        "missing_line_break",
        "mostly_english",
        "placeholder_leak",
        "too_literal",
        "untranslated_short_phrase",
    }
    return {
        item.line_index
        for item in quality.diagnostics
        if item.line_index > 0 and item.code in repairable_codes
    }


def _quality_gate(quality, repair_count: int) -> dict[str, Any]:
    diagnostics_by_code: dict[str, int] = {}
    for item in quality.diagnostics:
        diagnostics_by_code[item.code] = diagnostics_by_code.get(item.code, 0) + 1
    naturalness_codes = {"mostly_english", "cjk_leakage", "too_literal", "untranslated_short_phrase"}
    return {
        "critical_errors": len(quality.errors),
        "warning_count": len(quality.warnings),
        "repair_count": repair_count,
        "naturalness_flags": sum(diagnostics_by_code.get(code, 0) for code in naturalness_codes),
        "diagnostics_by_code": diagnostics_by_code,
        "ok": not quality.errors,
    }


def _default_model(settings: Settings, provider_name: str) -> str:
    if provider_name == "openai":
        return settings.openai.model
    if provider_name == "ollama":
        return settings.ollama.model
    if provider_name == "lmstudio":
        return settings.lmstudio.model
    return ""


def _effective_chunk_size(settings: Settings, options: TranslationJobOptions) -> int:
    if options.batch_size is not None:
        return options.batch_size
    preset = options.quality_preset or settings.translation.quality_preset
    if preset == "fast":
        return 10
    if preset == "balanced":
        return 8
    return settings.translation.chunk_size


def _write_job_state(settings: Settings, job_id: str, status: str, payload: dict[str, Any]) -> None:
    with _job_connection(settings) as connection:
        connection.execute(
            """
            INSERT INTO translation_jobs(job_id, status, payload_json, updated_at)
            VALUES(?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            ON CONFLICT(job_id) DO UPDATE SET
              status = excluded.status,
              payload_json = excluded.payload_json,
              updated_at = excluded.updated_at
            """,
            (job_id, status, json.dumps(payload, ensure_ascii=False)),
        )
        connection.commit()


def _job_connection(settings: Settings) -> sqlite3.Connection:
    settings.cache.path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.cache.path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS translation_jobs(
          job_id TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def _jsonable_options(options: TranslationJobOptions) -> dict[str, Any]:
    data = asdict(options)
    for key, value in list(data.items()):
        if isinstance(value, Path):
            data[key] = str(value)
    return data
