# Agent Guide

This file is for AI coding agents working on `anime-sub-ai`.

## Project Goal

Build a local-first anime subtitle translation pipeline:

```text
MKV with English ASS subtitles
-> Vietnamese ASS subtitle
-> original MKV remuxed with Vietnamese softsub track
```

Keep the scope focused. Do not add GUI, OCR, vision AI, Plex/Jellyfin integration, or local LLM management UI unless explicitly requested.

## Current Architecture

Main modules:

- `app/cli/main.py`: Typer CLI commands.
- `app/extractor/subtitle_extractor.py`: MKV subtitle track inspection and extraction.
- `app/parser/ass_parser.py`: ASS parsing using `pysubs2`.
- `app/translator/base.py`: provider interface and translation data models.
- `app/translator/chunker.py`: chunking with context overlap.
- `app/translator/prompt_builder.py`: provider prompts.
- `app/translator/openai_provider.py`: OpenAI implementation.
- `app/translator/ollama_provider.py`: Ollama implementation.
- `app/translator/lmstudio_provider.py`: LM Studio OpenAI-compatible implementation.
- `app/translator/factory.py`: provider registration.
- `app/translator/json_response.py`: model JSON response parsing.
- `app/translator/pipeline.py`: async chunk translation and split retry.
- `app/formatter/ass_formatter.py`: ASS rebuild.
- `app/quality/validator.py`: basic integrity checks and ASS tag reinjection.
- `app/muxer/mkv_muxer.py`: MKV softsub muxing.
- `app/config/settings.py`: YAML/env config loading.
- `tests/test_mvp.py`: focused MVP tests.

## Core Pipeline

```text
inspect MKV tracks
-> select English ASS track
-> extract subtitle to temp
-> parse ASS into SubtitleLine objects
-> chunk lines
-> provider translates chunk to strict JSON
-> validate indexes and line counts
-> preserve missing ASS tags
-> rebuild translated ASS
-> validate generated ASS
-> mux ASS into MKV
```

## Current Performance Findings

See `docs/BENCHMARKS.md`.

Key conclusion:

- Do not use reasoning models for fast subtitle translation.
- `qwen2.5-7b-instruct-1m` via LM Studio is currently the best local candidate.
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
- Keep provider-specific behavior behind provider classes.
- Keep CLI options provider-neutral where possible.
- Prefer small, focused tests for parsing, validation, chunking, provider factory behavior, and ASS rebuild.
- Do not commit generated files under `output/`, `temp/`, `cache/`, or `logs/`.

## Production Readiness Priorities

Before batch season use, implement:

1. SQLite translation cache.
2. Resume support for interrupted translation runs.
3. Per-chunk output files or durable job state.
4. Better JSON repair for local models.
5. Glossary and protected term support.
6. Automated provider benchmark command.
7. Quality report that separates errors from warnings.
8. Integration fixture with a tiny generated MKV and ASS track.

## Test Commands

```bash
python -m unittest discover -s tests
python -m compileall app
python -m app translate --help
```

For local LM Studio benchmark:

```bash
python -m app translate "episode.mkv" \
  --provider lmstudio \
  --model qwen2.5-7b-instruct-1m \
  --batch-size 8 \
  --max-concurrency 1 \
  --limit-lines 50 \
  --skip-mux
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
- Some local models drop ASS override tags.
- Reasoning models may take minutes for tiny chunks.
- `mkvmerge`, `mkvextract`, and `ffmpeg` may not be on PATH immediately after install on Windows; `app/utils/subprocess_runner.py` includes fallback discovery for common install paths.
