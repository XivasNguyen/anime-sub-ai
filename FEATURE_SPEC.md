# Anime AI Subtitle Pipeline — Implementation Plan

> Implementation plan for Claude Code.
> Target: build a local-first CLI tool that extracts English ASS subtitles from anime MKV files, translates them into Vietnamese using AI, and muxes the translated subtitle back into the original MKV as a softsub track.

---

## 1. Goal

Build a local-first AI subtitle translation pipeline for anime downloaded from sources such as SubsPlease or Nyaa.

The system must:

- Extract English ASS subtitles from MKV anime files.
- Translate subtitles into natural Vietnamese using AI.
- Preserve subtitle timing and ASS formatting.
- Preserve anime-specific tone, honorifics, names, jokes, and terminology.
- Generate Vietnamese `.ass` subtitle files.
- Mux translated subtitles back into the original MKV as softsubs.
- Avoid video/audio re-encoding.
- Support future GUI and automation expansion.

---

## 2. Final Output

### Input

```text
[SubsPlease] Anime Episode.mkv
```

### Output

```text
[SubsPlease] Anime Episode.vi.mkv
```

The output MKV should contain:

- Original video.
- Original audio.
- Original English subtitle track.
- New Vietnamese AI subtitle softsub track.

---

## 3. Core Design Principles

### 3.1. Do not OCR subtitles unless necessary

Anime releases from SubsPlease usually contain proper softsub English subtitle tracks.

Preferred workflow:

```text
Extract subtitle stream
→ Translate subtitle text
→ Rebuild ASS subtitle
→ Remux subtitle into MKV
```

Avoid this workflow unless there is no subtitle track:

```text
OCR frames
→ Speech recognition
→ Generate subtitle timings manually
```

### 3.2. Keep ASS format as long as possible

ASS subtitles contain:

- Styling.
- Positioning.
- Karaoke effects.
- Signs.
- Effects.
- Font assumptions.

Do not convert to SRT during the early pipeline.

### 3.3. Never translate line-by-line independently

Translation must preserve:

- Conversation context.
- Sarcasm.
- Character personality.
- Emotional flow.
- Speaker intent.

Use chunk-based translation instead of one API call per subtitle line.

---

## 4. Recommended Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Video tools | ffmpeg, mkvtoolnix |
| Subtitle parser | pysubs2 |
| AI provider | OpenAI API initially |
| Optional local AI | Ollama + Qwen/Qwen3 |
| CLI | Typer |
| GUI, future | Gradio |
| Packaging | Docker |
| Config | YAML |
| Logging | structlog |
| Cache | SQLite |

---

## 5. Suggested Repository Names

Recommended:

```text
anime-sub-ai
```

Other options:

```text
softsub-ai
anime-localizer
ass-ai-pipeline
context-subtitle-translator
mirai-sub
nekosub
```

Use `anime-sub-ai` unless there is a strong reason to choose a more branded name.

---

## 6. Project Structure

```text
anime-sub-ai/
├── app/
│   ├── __init__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   └── main.py
│   ├── extractor/
│   │   ├── __init__.py
│   │   └── subtitle_extractor.py
│   ├── parser/
│   │   ├── __init__.py
│   │   └── ass_parser.py
│   ├── translator/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── openai_provider.py
│   │   ├── prompt_builder.py
│   │   └── chunker.py
│   ├── glossary/
│   │   ├── __init__.py
│   │   └── glossary.py
│   ├── memory/
│   │   ├── __init__.py
│   │   └── translation_memory.py
│   ├── formatter/
│   │   ├── __init__.py
│   │   └── ass_formatter.py
│   ├── muxer/
│   │   ├── __init__.py
│   │   └── mkv_muxer.py
│   ├── quality/
│   │   ├── __init__.py
│   │   └── validator.py
│   ├── cache/
│   │   ├── __init__.py
│   │   └── sqlite_cache.py
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py
│   └── utils/
│       ├── __init__.py
│       └── subprocess_runner.py
├── output/
├── temp/
├── cache/
├── logs/
├── tests/
├── config.yaml
├── requirements.txt
├── Dockerfile
├── README.md
└── Plan.md
```

---

## 7. MVP Scope

### 7.1. Required Features

- Extract ASS subtitle from MKV.
- Parse ASS subtitle.
- Chunk subtitle for translation.
- Translate subtitle using AI.
- Preserve ASS formatting.
- Generate Vietnamese ASS.
- Mux Vietnamese ASS into original MKV.
- Provide CLI interface.

### 7.2. Not Required Yet

- OCR.
- Vision AI.
- GUI.
- Speaker detection.
- Batch folder watching.
- Jellyfin/Plex integration.

---

## 8. Module Specifications

### 8.1. Extractor Module

#### Responsibility

Extract subtitle tracks from MKV files.

#### Input

```text
episode.mkv
```

#### Output

```text
episode.en.ass
```

#### Preferred Tools

Use `mkvextract` first.

Fallback to `ffmpeg` only if needed.

#### Required Features

Detect subtitle streams using one of these:

```bash
ffprobe episode.mkv
```

```bash
mkvmerge -i episode.mkv
```

Select English subtitle track automatically with this priority:

1. ASS English track.
2. SRT English track.
3. First available subtitle track.

Ensure extracted subtitles are saved as UTF-8.

---

### 8.2. Subtitle Parser Module

#### Responsibility

Parse subtitle timing, text, and formatting.

#### Library

Use:

```python
pysubs2
```

#### Required Data Model

Each subtitle line should become an internal object similar to:

```python
{
    "index": 1,
    "start": 1000,
    "end": 3500,
    "style": "Default",
    "text": "You're an idiot!",
    "raw_text": "{\an8}You're an idiot!"
}
```

#### Must Preserve ASS Tags

Examples of ASS tags that must survive translation:

```text
{\an8}
{\i1}
{\c&HFFFFFF&}
```

The AI must not remove or corrupt these tags.

---

### 8.3. Translation Engine

#### Responsibility

Translate subtitles into Vietnamese with contextual awareness.

#### Critical Requirement

Do not translate one subtitle line per request.

Use chunk-based translation.

#### Translation Chunking

Recommended defaults:

```yaml
chunk_size: 12
overlap_lines: 2
```

Each chunk should include:

- Current subtitle lines to translate.
- A small number of previous lines for context.
- Optional character memory.
- Optional glossary.
- Translation rules.

#### Pipeline

```text
Subtitle chunk
→ Prompt builder
→ AI translation
→ JSON validation
→ ASS tag reinjection
→ Translation result
```

#### AI Provider

Initial provider:

```text
OpenAI GPT-5 or GPT-4.1
```

#### Provider Abstraction

Implement a base provider interface:

```python
from abc import ABC, abstractmethod

class TranslatorProvider(ABC):
    @abstractmethod
    async def translate(self, chunk):
        pass
```

Future providers:

- Gemini.
- DeepSeek.
- Ollama local models.

---

### 8.4. Prompt Builder

#### Responsibility

Build stable prompts for Vietnamese anime subtitle translation.

#### System Prompt Requirements

The prompt must instruct the model to:

- Translate naturally into Vietnamese.
- Preserve anime tone.
- Preserve humor, sarcasm, and emotional nuance.
- Avoid robotic Vietnamese.
- Avoid overly formal wording.
- Preserve honorifics when appropriate.
- Preserve ASS tags exactly.
- Return strict JSON only.
- Keep the same number of translated lines as input lines.

#### Expected AI Response Format

```json
{
  "translations": [
    {
      "index": 1,
      "translated_text": "Cậu đúng là đồ ngốc."
    },
    {
      "index": 2,
      "translated_text": "Cô ấy đang nói về nghi lễ đó!"
    }
  ]
}
```

---

### 8.5. Glossary System

#### Responsibility

Prevent incorrect translation of anime-specific terms.

#### Example Glossary

```json
{
  "senpai": "senpai",
  "onii-chan": "onii-chan",
  "guild": "guild",
  "mana": "mana"
}
```

#### Required Features

Protected terms should include:

- Names.
- Attack names.
- Faction names.
- World-specific terminology.
- Honorifics.
- Recurring anime terms.

Glossary should be configurable per anime series.

---

### 8.6. Translation Memory / Cache

#### Responsibility

Reduce API cost and improve translation consistency.

#### Cache Strategy

Use a hash based on:

```text
original_text + nearby_context + glossary_version + model_name
```

#### Storage

Use SQLite initially.

#### Benefits

- Reuse repeated phrases.
- Reuse OP/ED lyrics.
- Handle recap episodes more cheaply.
- Keep recurring wording consistent.

---

### 8.7. ASS Formatter

#### Responsibility

Rebuild translated ASS subtitle safely.

#### Must Preserve

- Timestamps.
- Styles.
- Karaoke tags.
- Positions.
- Effects.
- Font attachment assumptions.
- Existing non-dialogue metadata.

#### Validation

Validate the generated ASS file by loading it again:

```python
import pysubs2

pysubs2.load("episode.vi.ass")
```

If validation fails, stop the pipeline and show an actionable error.

---

### 8.8. Quality Control Module

#### Responsibility

Detect translation and subtitle integrity issues.

#### Required Checks

Line count check:

```text
input line count == output line count
```

Broken ASS tag check:

- Detect missing opening or closing braces.
- Detect corrupted override tags.
- Detect removed positioning tags.

Untranslated English check:

- Warn if a translated line remains mostly English.
- Ignore protected terms and names.

Empty translation check:

- Reject empty translated lines unless the original line is empty.

JSON validation:

- Reject malformed responses.
- Retry translation if needed.

---

### 8.9. Muxer Module

#### Responsibility

Mux Vietnamese subtitle back into the original MKV as a softsub track.

#### Preferred Tool

Use:

```text
mkvmerge
```

Do not use `ffmpeg` unless fallback is required.

#### Required Output

```text
episode.vi.mkv
```

#### Mux Requirements

Preserve:

- Video.
- Audio.
- Chapters.
- Attachments/fonts.
- Existing subtitles.
- Metadata where possible.

Add Vietnamese subtitle track with:

```text
language = vie
track name = Vietnamese AI
```

#### Example Command

```bash
mkvmerge -o output.mkv \
  original.mkv \
  --language 0:vie \
  --track-name 0:"Vietnamese AI" \
  translated.vi.ass
```

#### Optional Setting

Allow Vietnamese subtitle to be set as the default subtitle track.

Config key:

```yaml
mux:
  set_default_subtitle: true
```

---

## 9. CLI Interface

### Framework

Use:

```python
Typer
```

### Main Command

```bash
anime-sub translate episode.mkv
```

### Expected Output

```text
output/episode.vi.mkv
```

### Useful CLI Options

```bash
anime-sub translate episode.mkv \
  --provider openai \
  --model gpt-5 \
  --batch-size 12 \
  --keep-en-sub \
  --set-default-sub \
  --dry-run \
  --debug
```

### Suggested Commands

```bash
anime-sub inspect episode.mkv
anime-sub extract episode.mkv
anime-sub translate episode.mkv
anime-sub mux episode.mkv episode.vi.ass
anime-sub validate episode.vi.ass
```

---

## 10. Config System

### File

```text
config.yaml
```

### Example

```yaml
provider: openai

openai:
  api_key: env:OPENAI_API_KEY
  model: gpt-5

translation:
  chunk_size: 12
  overlap_lines: 2
  max_concurrency: 3
  retry_count: 3

mux:
  set_default_subtitle: true
  subtitle_language: vie
  subtitle_track_name: Vietnamese AI

glossary:
  enabled: true
  path: glossary/default.json

cache:
  enabled: true
  path: cache/translation_memory.sqlite

output:
  directory: output
```

---

## 11. Logging

### Requirements

Use structured logging.

Recommended library:

```python
structlog
```

### Log Events

Log the following events:

- Extraction started.
- Extraction completed.
- Subtitle track selected.
- Translation chunk started.
- Translation chunk completed.
- Translation retry.
- Malformed JSON.
- Quality warning.
- ASS validation success or failure.
- Mux started.
- Mux completed.

---

## 12. Error Handling

### Required Retry Logic

Retry translation if:

- AI response has malformed JSON.
- AI response has missing translations.
- AI response has empty translations.
- ASS output is corrupted.
- API timeout occurs.
- Rate limit occurs.

### Translation Fallback Flow

```text
Primary model
→ Retry same model
→ Split chunk into smaller chunks
→ Retry smaller chunks
→ Fail with detailed error report
```

---

## 13. Performance Considerations

### Async Translation

Use:

```python
asyncio
```

for chunk translation.

### Concurrency Limits

Respect provider rate limits.

Configurable key:

```yaml
translation:
  max_concurrency: 3
```

### Subtitle Chunk Cache

Cache translated chunks to avoid retranslation after failures.

---

## 14. Docker Support

### Requirements

Docker image must include:

- Python.
- ffmpeg.
- mkvtoolnix.
- Python dependencies.

### Example System Dependencies

```dockerfile
RUN apt-get update && apt-get install -y \
    ffmpeg \
    mkvtoolnix \
    && rm -rf /var/lib/apt/lists/*
```

---

## 15. Future Expansion Roadmap

### Phase 2

Add:

- GUI with Gradio.
- Batch season translation.
- Watch folders.
- Translation preview editor.
- Per-series glossary UI.

### Phase 3

Add:

- OCR sign translation.
- Scene-aware vision translation.
- Speaker detection.
- Translation consistency AI pass.
- Jellyfin/Plex integration.

### Phase 4

Add:

- Local-only LLM mode.
- GPU acceleration.
- Fully offline pipeline.
- Desktop app packaging.

---

## 16. Anime Translation Rules

### 16.1. Honorific Handling

Do not aggressively localize:

- senpai.
- sama.
- chan.
- kun.
- onii-chan.
- onee-sama.

These should be configurable through glossary rules.

### 16.2. Tone Preservation

The translation should:

- Sound natural in Vietnamese.
- Preserve humor.
- Preserve sarcasm.
- Preserve anime personality archetypes.
- Preserve emotional intensity.

Avoid:

- Robotic wording.
- Overly formal phrasing.
- Literal word-by-word translation.
- Unnecessary Vietnamese localization that changes character vibe.

### 16.3. Dialogue Style

Prefer conversational Vietnamese.

Anime subtitles should feel:

- Fast.
- Natural.
- Emotionally expressive.
- Easy to read in short subtitle timing windows.

---

## 17. Recommended Initial Development Order

### Step 1

Build subtitle extractor.

### Step 2

Build ASS parser.

### Step 3

Build AI translation prototype.

### Step 4

Implement chunk translation.

### Step 5

Implement ASS rebuild.

### Step 6

Implement muxing.

### Step 7

Add quality validation.

### Step 8

Add cache and glossary.

### Step 9

Add CLI polish and config support.

---

## 18. MVP Success Criteria

The MVP is successful if:

- User can run one CLI command.
- User receives a valid Vietnamese softsub MKV.
- Subtitle timing remains correct.
- ASS styling survives.
- Translation feels natural.
- No video/audio re-encoding occurs.
- Existing audio, video, chapters, fonts, and subtitle tracks are preserved.
