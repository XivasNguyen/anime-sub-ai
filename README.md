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

Not production-complete yet:

- Full GUI shell around the job/progress API
- Robust JSON repair for every malformed local-model output
- Full end-to-end quality review on a completed real episode
- Batch season processing
- GUI, OCR, vision AI, Plex/Jellyfin integration, local LLM management UI

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

Each translate run writes a JSON report next to the generated `.vi.ass` with timings, cache stats, warnings, knowledge metadata, and output paths.

Current benchmark notes are in [docs/BENCHMARKS.md](docs/BENCHMARKS.md).

Useful commands:

```bash
python -m app inspect "episode.mkv"
python -m app extract "episode.mkv"
python -m app validate "output/episode.vi.ass"
python -m app mux "episode.mkv" "output/episode.vi.ass"
```

## How The Engine Works

The current pipeline is:

```text
MKV input
-> inspect subtitle tracks
-> select English ASS/SRT subtitle track
-> extract subtitle to temp/*.en.ass
-> parse ASS events with pysubs2
-> split subtitle events into contextual chunks
-> translate each chunk with selected provider
-> validate JSON response and line indexes
-> reinject missing ASS override tags
-> rebuild translated ASS while preserving original styles/timing/metadata
-> validate generated ASS
-> mux translated ASS into the original MKV as a Vietnamese softsub track
```

The translation provider abstraction lives under `app/translator/`. New providers should implement `TranslatorProvider` from `app/translator/base.py` and be registered in `app/translator/factory.py`.

## Current Problem

The main bottleneck is not extraction, ASS parsing, rebuild, or muxing. Those steps are fast.

The bottleneck is local model behavior:

- Reasoning models can be extremely slow. A Qwen thinking model took about `159s` for a single subtitle line because almost all generated tokens were reasoning.
- Non-reasoning models are much faster. `qwen2.5-7b-instruct-1m` translated one line in about `0.7s`.
- Larger chunks improve throughput, but local models may return malformed or truncated JSON.
- For LM Studio, concurrency above `1` did not improve throughput in the current tests.

The project is moving toward a production-ready approach: benchmark first, choose model/batch settings based on evidence, add resumable cache, and make local-provider output repair more robust before full-season automation.
