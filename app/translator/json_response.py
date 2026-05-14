from __future__ import annotations

import json
from typing import Any

from app.translator.base import TranslationResult


class TranslationResponseError(RuntimeError):
    pass


def parse_translation_response(content: str, expected_indexes: set[int]) -> list[TranslationResult]:
    try:
        data: Any = json.loads(content)
    except json.JSONDecodeError as exc:
        raise TranslationResponseError(f"Malformed translation JSON: {exc}") from exc

    translations = data.get("translations") if isinstance(data, dict) else None
    if not isinstance(translations, list):
        raise TranslationResponseError("Translation JSON must contain a translations list.")

    results: list[TranslationResult] = []
    seen: set[int] = set()
    for item in translations:
        if not isinstance(item, dict):
            raise TranslationResponseError("Each translation entry must be an object.")
        index = item.get("index")
        translated_text = item.get("translated_text")
        if not isinstance(index, int) or not isinstance(translated_text, str):
            raise TranslationResponseError("Each translation requires integer index and string translated_text.")
        if index in seen:
            raise TranslationResponseError(f"Duplicate translation index: {index}")
        if index not in expected_indexes:
            raise TranslationResponseError(f"Unexpected translation index: {index}")
        seen.add(index)
        results.append(TranslationResult(index=index, translated_text=translated_text))

    missing = expected_indexes - seen
    if missing:
        raise TranslationResponseError(f"Missing translations for indexes: {sorted(missing)}")
    return sorted(results, key=lambda result: result.index)

