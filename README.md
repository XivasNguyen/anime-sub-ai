# anime-sub-ai
AI-powered local-first subtitle translation pipeline for anime MKV files.

The current MVP extracts English ASS subtitles from an MKV, translates them to Vietnamese with a selected AI provider, rebuilds the ASS file while preserving timing/style metadata, and muxes the translated subtitle back into the original MKV as a softsub track.

## Current Status

Implemented:

- CLI commands for `inspect`, `extract`, `translate`, `validate`, and `mux`
- CLI `benchmark` command for local provider/batch-size tuning
- MKV subtitle detection and extraction with `mkvmerge`/`mkvextract`, with FFmpeg fallback
- ASS parsing and rebuilding with `pysubs2`
- Chunked AI translation
- Providers: `openai`, `ollama`, `lmstudio`
- Local LM Studio partial benchmarking with `--limit-lines` and `--skip-mux`
- Basic validation and deterministic reinjection of missing ASS override tags
- MKV softsub muxing with `mkvmerge`
- SQLite translation cache and resumable chunk reuse
- Durable translation job state and machine-readable JSON reports
- Optional cached series knowledge base plus auto-extracted glossary
- ASS tag masking before translation and deterministic restoration after translation
- Basic local-model JSON repair for common malformed responses
- Dual-source translation scaffolding with local `faster-whisper` Japanese ASR and timestamp alignment
- Production presets for quality/repair behavior and ASR model/device selection
- Local web GUI with FastAPI/Jinja2
- Per-line quality diagnostics in JSON reports
- Manual glossary file support
- Human review set export
- Windows PyInstaller build and GitHub release scaffolding

Not production-complete yet:

- Polished GUI review editor UX
- Production-grade natural Vietnamese output
- Reliable CUDA ASR setup and audio-assisted translation by default
- Strong series knowledge base with character relationships and pronoun policy
- Batch season processing
- OCR, vision AI, Plex/Jellyfin integration, local LLM management UI

## Getting Started
Install Python dependencies:

```bash
pip install -r requirements.txt
```

Install system tools:

- `mkvtoolnix` for `mkvmerge` and `mkvextract`
- `ffmpeg` for `ffprobe` and fallback extraction

Set your OpenAI key:

```bash
export OPENAI_API_KEY=...
```

Run the MVP pipeline:

```bash
python -m app translate "episode.mkv"
```

Start the local web GUI:

```bash
python -m app web
```

Use OpenAI:

```bash
python -m app translate "episode.mkv" --provider openai --model gpt-5
```

Use a local Ollama model:

```bash
ollama pull qwen2.5:14b
python -m app translate "episode.mkv" --provider ollama --model qwen2.5:14b
```

Use LM Studio:

1. Start LM Studio's local server.
2. Load a non-reasoning chat/instruct model.
3. Run:

```bash
python -m app translate "episode.mkv" --provider lmstudio --model local-model
```

The default LM Studio endpoint is `http://localhost:1234/v1`. Override it with:

```bash
set LMSTUDIO_BASE_URL=http://localhost:1234/v1
set LMSTUDIO_MODEL=local-model
```

Recommended local model class:

- Prefer fast non-reasoning instruct models, such as `qwen2.5-7b-instruct`, `gemma-3-4b-it`, `mistral-7b-instruct`, or `llama-3.1-8b-instruct`.
- Avoid reasoning models for this workflow, such as `deepseek-r1*` or Qwen thinking models, unless thinking is definitely disabled. They can spend most of the time generating reasoning instead of subtitles.

## Benchmark Before Full Translation

Always benchmark a small slice before translating a full episode:

```bash
python -m app translate "episode.mkv" \
  --provider lmstudio \
  --model qwen2.5-7b-instruct-1m \
  --batch-size 8 \
  --max-concurrency 1 \
  --limit-lines 50 \
  --skip-mux
```

Useful local options:

- `--limit-lines N`: translate only the first N subtitle events.
- `--start-line N`: start from a later subtitle event.
- `--skip-mux`: write only the `.ass` file, no MKV muxing.
- `--batch-size N`: number of subtitle lines per model request.
- `--max-concurrency N`: concurrent translation requests. For LM Studio, `1` is usually safest.
- `--resume/--no-resume`: reuse or bypass completed cached chunks.
- `--force-retranslate`: ignore cached translations for this run.
- `--repair-warnings`: run a second translation pass only for lines flagged by quality warnings.
- `--repair-mode none|warnings|production`: choose targeted repair behavior.
- `--quality-preset fast|balanced|production`: choose batch defaults and future quality gates.
- `--dual-source/--no-dual-source`: include or bypass Japanese audio ASR context.
- `--asr-model turbo|small|medium|large-v3`: choose the local faster-whisper model.
- `--asr-device cuda|cpu`: choose the ASR runtime device.
- `--glossary-path PATH`: use a manual glossary JSON file.
- `--series-title NAME`: override filename-based title inference for knowledge/glossary.
- `--knowledge`: enable cached series knowledge enrichment.
- `--knowledge-web`: allow one cached web metadata lookup for the series.
- `--spoiler-mode no_spoiler|episode_safe|full_lore`: choose how much external context is allowed.

Run a batch-size benchmark:

```bash
python -m app benchmark "episode.mkv" \
  --provider lmstudio \
  --model qwen2.5-7b-instruct-1m \
  --lines 50 \
  --batch-sizes 6,8,10,12
```

Each translate run writes a JSON report next to the generated `.vi.ass` with timings, cache stats, warnings, per-line diagnostics, knowledge metadata, and output paths.

Recent local test:

```text
Input: [SubsPlease] NEEDY GIRL OVERDOSE - 07 (720p) [129E318F].mkv
Provider/model: LM Studio / gemma-3-4b-it
Mode: no dual-source ASR, production repair, batch 8, concurrency 1
Lines: 361
Elapsed: 263.7s
Speed: 1.37 lines/s
Critical errors: 0
Warnings: 57
Remaining quality issues: mostly English fragments, pronoun/register shifts, and high CPS lines
```

This is fast enough for the current five-minute target, but it is not yet production-quality Vietnamese. The translation still sounds stiff in many places, so the next major work is audio-backed context plus a stronger series knowledge/RAG layer.

Current benchmark notes are in [docs/BENCHMARKS.md](docs/BENCHMARKS.md).

Useful commands:

```bash
python -m app inspect "episode.mkv"
python -m app extract "episode.mkv"
python -m app validate "output/episode.vi.ass"
python -m app mux "episode.mkv" "output/episode.vi.ass"
python -m app export-review "temp/episode.en.ass" "output/episode.vi.ass" --output review/episode.json
```

## How The Engine Works

The current pipeline is:

```text
MKV input
-> inspect subtitle tracks
-> select English ASS/SRT subtitle track
-> extract subtitle to temp/*.en.ass
-> parse ASS events with pysubs2
-> optionally extract Japanese audio and align ASR text to subtitle timings
-> split subtitle events into contextual chunks
-> translate each chunk with selected provider
-> validate JSON response and line indexes
-> reinject missing ASS override tags
-> rebuild translated ASS while preserving original styles/timing/metadata
-> validate generated ASS
-> mux translated ASS into the original MKV as a Vietnamese softsub track
```

The translation provider abstraction lives under `app/translator/`. New providers should implement `TranslatorProvider` from `app/translator/base.py` and be registered in `app/translator/factory.py`.

## Manual Glossary

Manual glossary terms live in `glossary/default.json` by default:

```json
{
  "terms": [
    {
      "source": "Ayanokoji",
      "target": "Ayanokoji",
      "note": "Character name",
      "protected": true
    }
  ]
}
```

Glossary precedence:

```text
manual glossary > cached series bible > auto-detected terms
```

## Knowledge And Audio Roadmap

The current knowledge base is intentionally conservative and can miss the real cast/persona context, which causes unstable Vietnamese pronouns. Production translation needs a richer per-series bible:

- Resolve the anime title to stable external IDs across MAL, AniList, AniDB, and optionally other mapping services.
- Fetch character lists, aliases, roles, Japanese names, voice actors, short bios, and relationship hints.
- Store those facts locally as structured JSON plus a small retrieval index.
- Retrieve only episode-relevant facts into each translation chunk instead of stuffing the whole series page into every prompt.
- Keep relationship facts spoiler-aware: no future-episode relationship facts in `no_spoiler` mode.

Useful references:

- Jikan exposes MAL-derived anime character/staff models, useful for a no-auth first pass: https://docs.jikan.moe/objects/model/anime/characters-and-staff/
- AniList GraphQL character connections include edge metadata such as character role and voice actors: https://anilist.gitbook.io/anilist-apiv2-docs/docs/guide/graphql/connections
- AniDB documents strict character relationship semantics and warns against casual scraping/over-requesting: https://wiki.anidb.net/Content%3ACharacters and https://wiki.anidb.net/API

Open work is tracked in [docs/PENDING_TASKS.md](docs/PENDING_TASKS.md).

## Windows Build And Release

Build a Windows package:

```powershell
.\scripts\build_windows.ps1
```

Run smoke checks:

```powershell
.\scripts\smoke_windows.ps1
```

The Windows release does not bundle FFmpeg or MKVToolNix. Install them separately:

```powershell
winget install Gyan.FFmpeg
winget install MoritzBunkus.MKVToolNix
```

GitHub releases are built from tags named `v*` by `.github/workflows/release.yml`.

## Current Problem

The main bottleneck is not extraction, ASS parsing, rebuild, or muxing. Those steps are fast.

The bottleneck is local model behavior:

- Reasoning models can be extremely slow. A Qwen thinking model took about `159s` for a single subtitle line because almost all generated tokens were reasoning.
- Non-reasoning models are much faster. `qwen2.5-7b-instruct-1m` translated one line in about `0.7s`.
- Larger chunks improve throughput, but local models may return malformed or truncated JSON.
- For LM Studio, concurrency above `1` did not improve throughput in the current tests.

The project is moving toward a production-ready approach: benchmark first, choose model/batch settings based on evidence, add resumable cache, and make local-provider output repair more robust before full-season automation.

Current quality conclusion:

- `gemma-3-4b-it` can meet the speed target, but output quality only improves slightly over the previous baseline.
- Without audio context and richer character knowledge, the model still produces stiff Vietnamese, inconsistent pronouns, and occasional English leakage.
- CUDA ASR currently needs environment repair on Windows when `cublas64_12.dll` is missing.
