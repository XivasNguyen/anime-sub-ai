# CLAUDE.md

Guidance for Claude Code and similar agents working in this repository.

## What This Project Is

`anime-sub-ai` is a Python CLI pipeline for translating anime soft subtitles. The MVP should remain focused on:

- CLI
- subtitle extraction
- ASS parsing
- chunked AI translation
- ASS rebuild
- MKV softsub muxing
- validation

Do not add GUI, OCR, vision AI, Jellyfin/Plex integration, or local LLM management unless the user explicitly asks.

## Important Commands

Run tests:

```bash
python -m unittest discover -s tests
```

Compile check:

```bash
python -m compileall app
```

Inspect MKV:

```bash
python -m app inspect "episode.mkv"
```

Dry run:

```bash
python -m app translate "episode.mkv" --provider lmstudio --model qwen2.5-7b-instruct-1m --dry-run
```

Partial benchmark:

```bash
python -m app translate "episode.mkv" --provider lmstudio --model qwen2.5-7b-instruct-1m --batch-size 8 --max-concurrency 1 --limit-lines 50 --skip-mux
```

## Design Constraints

- Keep translation text separate from ASS timing and style metadata.
- The model should only translate event text.
- Code must preserve timing, style names, metadata, chapters, attachments, and original streams.
- Prefer deterministic repair in Python over trusting local models to preserve formatting.
- Provider implementations must stay isolated and registered through `app/translator/factory.py`.

## Current Provider Notes

Supported providers:

- `openai`
- `ollama`
- `lmstudio`

LM Studio default:

```text
http://localhost:1234/v1
```

The local model target is under 5 minutes for one episode, but this depends heavily on model choice. Avoid reasoning models. `qwen2.5-7b-instruct-1m` is currently much faster than `qwen/qwen3.5-9b`.

## Current Problem To Solve

The current bottleneck is local model reliability and speed, not video processing.

Observed issues:

- Reasoning models generate thousands of reasoning tokens and are too slow.
- Local instruct models can be fast but sometimes return malformed JSON.
- Larger chunks can improve speed but increase malformed or truncated responses.
- Local models sometimes drop ASS tags.

Current mitigations:

- Partial benchmark options: `--limit-lines`, `--start-line`, `--skip-mux`.
- `--max-concurrency` override.
- Compact LM Studio prompt.
- JSON extraction from prose/code fences.
- Relaxed JSON parsing.
- Split failed chunks into smaller chunks.
- Reinject missing ASS override tags before validation.

## Production-Ready Direction

Next features should improve durability and repeatability:

1. Translation cache and resumable jobs.
2. Per-chunk status persistence.
3. Structured benchmark command.
4. Stronger local model JSON repair.
5. Glossary and protected terms.
6. Better quality reporting.
7. Small MKV integration fixture.
8. Full episode E2E test after benchmark confidence.

## Git Hygiene

- Do not commit `output/`, `temp/`, `cache/`, or `logs/`.
- Preserve user files and unrelated changes.
- Before committing code changes, run:

```bash
python -m unittest discover -s tests
python -m compileall app
```

## Files To Read First

1. `FEATURE_SPEC.md`
2. `README.md`
3. `docs/BENCHMARKS.md`
4. `AGENT.md`
5. `app/cli/main.py`
6. `app/translator/factory.py`
7. `app/translator/pipeline.py`
