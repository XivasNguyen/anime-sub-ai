# Agent Guide

This file is for AI coding agents working on `anime-sub-ai`.

## Project Goal

Build a local-first anime subtitle translation pipeline:

```text
MKV with English ASS subtitles
-> Vietnamese ASS subtitle
-> original MKV remuxed with Vietnamese softsub track
```

Keep the scope focused. Do not add OCR, vision AI, Plex/Jellyfin integration, or local LLM management UI unless explicitly requested.
The local web GUI must call the same job service as the CLI; do not duplicate pipeline logic in web routes.

## Current Architecture

Main modules:

- `app/cli/main.py`: Typer CLI commands.
- `app/extractor/subtitle_extractor.py`: MKV subtitle track inspection and extraction.
- `app/parser/ass_parser.py`: ASS parsing using `pysubs2`.
- `app/translator/base.py`: provider interface and translation data models.
- `app/translator/chunker.py`: chunking with context overlap.
- `app/translator/prompt_builder.py`: provider prompts.
- `app/translator/ass_mask.py`: deterministic ASS override tag masking/restoration.
- `app/translator/openai_provider.py`: OpenAI implementation.
- `app/translator/ollama_provider.py`: Ollama implementation.
- `app/translator/lmstudio_provider.py`: LM Studio OpenAI-compatible implementation.
- `app/translator/factory.py`: provider registration.
- `app/translator/json_response.py`: model JSON response parsing.
- `app/translator/pipeline.py`: async chunk translation, split retry, cache lookup/write, provider cleanup.
- `app/cache/sqlite_cache.py`: SQLite translation cache keyed by provider/model/prompt/glossary/ASS versions.
- `app/jobs/service.py`: durable local translation job runner used by CLI and intended for future GUI.
- `app/jobs/report.py`: machine-readable JSON translation reports.
- `app/knowledge/series_bible.py`: optional cached series metadata/knowledge base.
- `app/glossary/glossary.py`: auto-extracted glossary and protected terms.
- `app/quality/report.py`: per-line quality diagnostics.
- `app/review/export.py`: human review/golden set export.
- `app/web/main.py`: FastAPI local web GUI and API.
- `app/formatter/ass_formatter.py`: ASS rebuild.
- `app/quality/validator.py`: integrity checks, glossary warnings, timing-length warnings, ASS tag reinjection fallback.
- `app/muxer/mkv_muxer.py`: MKV softsub muxing.
- `app/config/settings.py`: YAML/env config loading.
- `tests/test_mvp.py`: focused MVP tests.

## Core Pipeline

```text
inspect MKV tracks
-> select English ASS track
-> extract subtitle to temp
-> parse ASS into SubtitleLine objects
-> optional cached series knowledge lookup
-> auto-build glossary/protected terms
-> chunk lines
-> mask ASS tags as placeholders
-> provider translates chunk to strict JSON
-> repair common malformed JSON
-> restore ASS tags deterministically
-> validate indexes, line counts, glossary, timing, and ASS integrity
-> rebuild translated ASS
-> validate generated ASS
-> write JSON report
-> mux ASS into MKV
```

## Current Performance Findings

See `docs/BENCHMARKS.md`.

Key conclusion:

- Do not use reasoning models for fast subtitle translation.
- `qwen2.5-7b-instruct-1m` via LM Studio is currently the best local candidate.
- `--batch-size 8 --max-concurrency 1` remains the best observed setting for LM Studio.
- Latest local benchmark on the documented 382-line test episode:
  - 50 lines, batch 8: `20.8s`, `2.40 lines/s`, estimated 382-line translation time `159s`.
  - 100 lines, batch 8: `59.3s`, `1.69 lines/s`, estimated 382-line translation time `226s`.
  - Batch 10/12 were slower because retries and long chunks offset fewer requests.
- Recommended LM Studio settings for the current test episode:

```bash
--batch-size 8
--max-concurrency 1
```

## Development Rules

- Preserve ASS as ASS. Do not convert to SRT for translation.
- Do not translate line-by-line for full runs; use chunking.
- Do not let the model own timing, styles, metadata, or muxing.
- Preserve ASS override tags deterministically in code where possible.
- Use ASS masking/restoration instead of relying on the model to preserve raw `{...}` tags.
- Keep web knowledge optional, cached, and preflight-only. Never fetch web data per translation chunk.
- Default spoiler mode is `no_spoiler`.
- Keep provider-specific behavior behind provider classes.
- Keep CLI options provider-neutral where possible.
- Prefer small, focused tests for parsing, validation, chunking, provider factory behavior, and ASS rebuild.
- Do not commit generated files under `output/`, `temp/`, `cache/`, or `logs/`.

## Production Readiness Priorities

Already implemented in commits `064fa87` and `c77ae70`:

- SQLite translation cache and chunk reuse.
- Durable job state and JSON reports.
- Optional series knowledge base and auto glossary.
- ASS tag masking/restoration.
- Basic JSON repair for common local-model output failures.
- `benchmark` command for batch-size tuning.
- Provider cleanup to avoid Windows `Event loop is closed` noise.

Remaining priorities:

1. Full real-episode E2E run and review, including muxed MKV playback.
2. Small generated MKV integration fixture for CI.
3. Better subtitle quality heuristics with fewer false positives.
4. Polished GUI review editor.
5. Full Windows release smoke with packaged executable.

## Test Commands

```bash
python -m unittest discover -s tests
python -m compileall app
python -m app translate --help
python -m app benchmark --help
python -m app web --help
```

For local LM Studio benchmark:

```bash
python -m app benchmark "episode.mkv" \
  --provider lmstudio \
  --model qwen2.5-7b-instruct-1m \
  --lines 50 \
  --batch-sizes 6,8,10,12
```

For a focused partial translation:

```bash
python -m app translate "episode.mkv" \
  --provider lmstudio \
  --model qwen2.5-7b-instruct-1m \
  --batch-size 8 \
  --max-concurrency 1 \
  --limit-lines 100 \
  --skip-mux \
  --no-knowledge
```

## Adding A Provider

1. Implement `TranslatorProvider` from `app/translator/base.py`.
2. Return `list[TranslationResult]`.
3. Reuse `parse_translation_response` when the provider returns JSON text.
4. Add settings in `app/config/settings.py`.
5. Register in `app/translator/factory.py`.
6. Add tests in `tests/test_mvp.py`.
7. Document usage in `README.md`.

## Known Failure Modes

- LM Studio local models may return JSON wrapped in prose or markdown.
- Some local models truncate JSON for large chunks.
- Some local models can still drop placeholders or return malformed JSON beyond current repair.
- Auto glossary extraction can still produce noisy warnings; it is better than before but not final QC.
- Reasoning models may take minutes for tiny chunks.
- Knowledge web lookup is optional and cached; network failures should degrade to local title/glossary only.
- `mkvmerge`, `mkvextract`, and `ffmpeg` may not be on PATH immediately after install on Windows; `app/utils/subprocess_runner.py` includes fallback discovery for common install paths.
