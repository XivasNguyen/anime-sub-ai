# CLAUDE.md

Guidance for Claude Code and similar agents working in this repository.

## What This Project Is

`anime-sub-ai` is a Python CLI pipeline for translating anime soft subtitles. The MVP should remain focused on:

- CLI
- subtitle extraction
- ASS parsing
- chunked AI translation
- local job state/cache/reporting
- optional cached series knowledge/glossary
- ASS rebuild
- MKV softsub muxing
- validation

Do not add OCR, vision AI, Jellyfin/Plex integration, or local LLM management unless the user explicitly asks. The local web GUI should remain a thin shell around `app/jobs/service.py`.

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
python -m app benchmark "episode.mkv" --provider lmstudio --model qwen2.5-7b-instruct-1m --lines 50 --batch-sizes 6,8,10,12
```

Focused partial translation:

```bash
python -m app translate "episode.mkv" --provider lmstudio --model qwen2.5-7b-instruct-1m --batch-size 8 --max-concurrency 1 --limit-lines 100 --skip-mux --no-knowledge
```

## Design Constraints

- Keep translation text separate from ASS timing and style metadata.
- The model should only translate event text.
- Code must preserve timing, style names, metadata, chapters, attachments, and original streams.
- Prefer deterministic repair in Python over trusting local models to preserve formatting.
- ASS override tags should be masked before translation and restored after translation.
- Web/series knowledge must be optional, cached, and run once per job/series, never per chunk.
- Default spoiler mode is `no_spoiler`.
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

Recommended LM Studio defaults:

```text
batch_size = 8
max_concurrency = 1
knowledge = disabled unless requested
```

Latest observed benchmark on the 382-line test episode:

- 50 lines, batch 8: `20.8s`, `2.40 lines/s`, estimated 382-line translation time `159s`.
- 100 lines, batch 8: `59.3s`, `1.69 lines/s`, estimated 382-line translation time `226s`.
- Batch 10 and 12 were slower because larger chunks caused retries and long generations.

## Current Problem To Solve

The current bottleneck is local model reliability and speed, not video processing.

Observed issues:

- Reasoning models generate thousands of reasoning tokens and are too slow.
- Local instruct models can be fast but sometimes return malformed JSON.
- Larger chunks can improve speed but increase malformed or truncated responses.
- Local models sometimes drop ASS tags.

Current mitigations:

- Partial benchmark options: `--limit-lines`, `--start-line`, `--skip-mux`.
- Structured `benchmark` command.
- `--max-concurrency` override.
- Compact LM Studio prompt.
- JSON extraction from prose/code fences.
- Relaxed JSON parsing.
- Basic JSON repair for common malformed local-model responses.
- Split failed chunks into smaller chunks.
- Mask/restore ASS override tags in code, with reinjection fallback before validation.
- SQLite cache and job state for resumable chunk reuse.
- JSON report beside generated subtitles.
- Optional cached series knowledge base and auto glossary.
- Manual glossary support.
- Per-line quality diagnostics.
- Local web GUI shell.
- Windows release scaffolding.

## Production-Ready Direction

Recently implemented:

- `app/jobs/service.py`: durable job runner and future GUI boundary.
- `app/cache/sqlite_cache.py`: translation cache.
- `app/knowledge/series_bible.py`: optional cached KB.
- `app/glossary/glossary.py`: auto glossary/protected terms.
- `app/translator/ass_mask.py`: ASS tag placeholders.
- CLI `benchmark`.

Next features:

1. Full real-episode E2E run and playback review.
2. Small MKV integration fixture for CI.
3. Better warning quality and fewer false positives.
4. Polished GUI review editor.
5. Full Windows package smoke test.

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
