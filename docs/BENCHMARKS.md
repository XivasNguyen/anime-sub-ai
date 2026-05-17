# Benchmarks

Benchmark file for local translation provider experiments.

## Test Environment

- OS: Windows
- Project root: `D:\anime-sub-ai`
- Runtime tools:
  - MKVToolNix `98.0`
  - FFmpeg `8.1.1`
- Test MKV:
  - `D:\[SubsPlease] Youkoso Jitsuryoku Shijou Shugi no Kyoushitsu e S4 - 10 (1080p) [DF62F816].mkv`
- Extracted subtitle:
  - English ASS
  - `382` subtitle events
- LM Studio endpoint:
  - `http://127.0.0.1:1234/v1`

## Loaded LM Studio Models Observed

- `qwen/qwen3.5-9b`
- `qwen2.5-7b-instruct-1m`
- `gemma-3-4b-it`
- `deepseek-r1-distill-qwen-7b`
- `text-embedding-nomic-embed-text-v1.5`

Do not use embedding models for translation.

## Results

| Provider | Model | Lines | Batch | Concurrency | Result | Notes |
|---|---:|---:|---:|---:|---:|---|
| LM Studio | `qwen/qwen3.5-9b` | 1 | 1 | 1 | `159.3s` | Not viable. Model generated heavy reasoning. |
| LM Studio | `qwen2.5-7b-instruct-1m` | 1 | 1 | 1 | `0.7s` | Good speed. |
| LM Studio | `qwen2.5-7b-instruct-1m` | 5 | 1 | 1 | `2.8s` | Five separate chunks. |
| LM Studio | `qwen2.5-7b-instruct-1m` | 5 | 5 | 1 | `2.4s` | One chunk. Slightly better. |
| LM Studio | `qwen2.5-7b-instruct-1m` | 20 | 10 | 1 | `10.9s` | Good speed. |
| LM Studio | `qwen2.5-7b-instruct-1m` | 20 | 20 | 1 | `24.7s` | Larger chunk was slower. |
| LM Studio | `qwen2.5-7b-instruct-1m` | 20 | 10 | 2 | `11.7s` | Concurrency did not help. |
| LM Studio | `qwen2.5-7b-instruct-1m` | 50 | 8 | 1 | `25.1s` | Stable, estimated about 3.2 minutes for translation only. |
| LM Studio | `qwen2.5-7b-instruct-1m` | 50 | 12 | 1 | `24.6s` | Similar speed, but bigger chunks later showed reliability risk. |
| LM Studio | `qwen2.5-7b-instruct-1m` | 100 | 8 | 1 | `54.7s` | Translation completed but validation caught dropped ASS tag before tag reinjection was added. |
| LM Studio | `qwen2.5-7b-instruct-1m` | 100 | 8 | 1 | `87.1s` | Succeeded after tag reinjection and split retry; forecast about 5.5-6 minutes full episode. |
| LM Studio | `gemma-3-4b-it` | 361 | 8 | 1 | `263.7s` | Completed full NEEDY GIRL OVERDOSE ep. 7 under 5 minutes with `--no-dual-source`; 0 critical errors, 57 warnings, quality still stiff. |

## Interpretation

The full episode has `382` lines. To finish under 5 minutes, the translation path needs at least:

```text
382 lines / 300 seconds = 1.27 lines/sec
```

Observed:

- `qwen/qwen3.5-9b`: about `0.006 lines/sec`; impossible for this target.
- `qwen2.5-7b-instruct-1m`: ranges from about `1.15` to `1.99 lines/sec`, depending on chunk stability and retry cost.

`qwen2.5-7b-instruct-1m` is close to the target but not consistently under 5 minutes yet. The likely production setting is:

```bash
--provider lmstudio
--model qwen2.5-7b-instruct-1m
--batch-size 8
--max-concurrency 1
```

## Current Risks

- Local models sometimes return malformed JSON.
- Local models sometimes drop ASS override tags.
- Local models may mix non-Vietnamese text into a translation.
- Retry splitting improves reliability but increases time.
- Translation cache and retry splitting reduce rerun cost, but malformed single-line responses can still fail.
- `gemma-3-4b-it` meets the speed target but still leaves English fragments, inconsistent pronoun/register choices, and high-CPS lines.
- Dual-source ASR is blocked on Windows CUDA setups that do not have the required cuBLAS runtime available.

## Next Optimization Work

1. Fix Windows CUDA ASR runtime and benchmark `--dual-source` with `turbo`.
2. Build a character/persona knowledge base with relationship-aware retrieval.
3. Add a pronoun/register critic and repair pass.
4. Add a polished GUI review editor for diagnostics.
5. Build a golden review set for 30-50 representative lines.
