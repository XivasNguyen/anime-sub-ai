# Changelog

## 0.4.0

- Added dual-source translation scaffolding with local `faster-whisper` ASR, timestamp overlap alignment, and prompt payload support for Japanese ASR context.
- Added production translation controls: `--dual-source`, `--asr-model`, `--asr-device`, `--quality-preset`, and `--repair-mode`.
- Hardened local-model output handling for malformed JSON placeholder escapes and unbalanced ASS braces.
- Reduced auto-glossary false positives by protecting only manual terms, honorifics, subtitle speaker names, and clear suffix-based names.
- Added quality report fields for dual-source status, repair counts, naturalness flags, and diagnostics grouped by code.
- Documented the `gemma-3-4b-it` full-episode test: fast enough under five minutes, but still not production quality without stronger audio and knowledge context.

## 0.3.0

- Added a Windows local file picker for MKV selection in the web GUI.
- Improved Translate status indicators with distinct idle, running, success, warning, and error states.
- Polished Provider dropdown alignment and Translate form controls.
- Added clearer job state updates for inspect, benchmark, translate, cancel, and stream errors.

## 0.2.0

- Redesign the GUI in a dark modern/futuristic/electric style.

## 0.1.0

- Added CLI subtitle extraction, ASS parsing, chunked translation, ASS rebuild, and MKV softsub muxing.
- Added OpenAI, Ollama, and LM Studio providers.
- Added SQLite cache, job reports, benchmark workflow, ASS masking, and glossary support.
- Added local web GUI skeleton and Windows release scaffolding.
