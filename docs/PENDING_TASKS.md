# Pending Production Tasks

This project is not production-ready yet. The latest `gemma-3-4b-it` test proved the speed target is reachable, but translation quality remains too stiff and inconsistent without audio and richer series knowledge.

## P0 - Audio Context

- Fix Windows CUDA ASR runtime: `faster-whisper` currently fails when `cublas64_12.dll` cannot be loaded.
- Add an ASR preflight check that reports CUDA, compute type, model availability, and expected fallback before a long translation starts.
- Benchmark `--dual-source --asr-model turbo --asr-device cuda` after CUDA is fixed.
- Add CPU fallback mode that is explicit and warns when it will likely exceed the 5-minute target.
- Store aligned ASR text in the report/review export so bad alignment can be inspected line by line.

## P0 - Knowledge Base And RAG

- Replace the thin series bible with a multi-source resolver:
  - Jikan/MAL for title aliases, synopsis, character/staff list.
  - AniList GraphQL for character role edges and voice actors.
  - AniDB for relationship semantics and title matching, without scraping pages or over-requesting.
- Add cross-site ID mapping and cache it locally per series title.
- Store structured facts:
  - titles and aliases
  - characters and aliases
  - roles: main/support/background
  - relationships with source and spoiler level
  - speaking style, age/social role, and pronoun hints
  - protected terms and official names
- Build a small retrieval layer that selects only relevant character/relationship facts for the current chunk.
- Add spoiler modes:
  - `no_spoiler`: only non-plot identity facts and current subtitle evidence
  - `episode_safe`: facts up to current episode if available
  - `full_lore`: all cached facts

## P0 - Vietnamese Naturalness

- Add a pronoun/register policy per character pair.
- Add a critic pass for stiff Vietnamese, English word order, and random pronoun switching.
- Add targeted repair prompts that include source line, current translation, speaker, nearby dialogue, and relevant knowledge facts.
- Add hard checks for raw English leakage in short lines and mixed English/Vietnamese clauses.
- Add high-CPS shortening repair instead of only warning.

## P1 - Review Workflow

- Add a side-by-side review UI:
  - English ASS source
  - Japanese ASR
  - Vietnamese output
  - diagnostics
  - expected fix
  - reviewer notes
- Let reviewers approve/reject generated fixes and save a golden set.
- Feed approved golden rows into regression tests.

## P1 - Reliability

- Continue hardening JSON repair for local model quirks.
- Add a final ASS sanitizer pass that removes model-invented malformed tags while preserving original source tags.
- Record failed raw model responses in debug artifacts when `--debug` is enabled.
- Make cache keys include all quality-affecting settings, including knowledge/RAG version and ASR alignment version.

## Research Notes

- Jikan can provide MAL-derived character/staff data without official MAL auth, making it good for first-pass metadata: https://docs.jikan.moe/objects/model/anime/characters-and-staff/
- AniList GraphQL exposes character connections with edge metadata such as role and voice actors, which fits a structured knowledge graph well: https://anilist.gitbook.io/anilist-apiv2-docs/docs/guide/graphql/connections
- AniDB is useful for relationship semantics, but its API documentation explicitly discourages HTML scraping and warns against excessive requests: https://wiki.anidb.net/API
- AniDB relationship rules are intentionally long-term and spoiler-sensitive; mirror that philosophy when generating pronoun/persona facts: https://wiki.anidb.net/Content%3ACharacters
