from __future__ import annotations

import json
from typing import Any

from app.translator.base import TranslationResult


class TranslationResponseError(RuntimeError):
    pass


def parse_translation_response(content: str, expected_indexes: set[int]) -> list[TranslationResult]:
    content = _extract_json_object(content)
    try:
        data: Any = json.loads(content, strict=False)
    except json.JSONDecodeError as exc:
        repaired = _repair_json(content)
        try:
            data = json.loads(repaired, strict=False)
        except json.JSONDecodeError:
            preview = content[:300].replace("\n", "\\n")
            raise TranslationResponseError(f"Malformed translation JSON: {exc}. Response starts with: {preview}") from exc

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


def _extract_json_object(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    if text.startswith("{"):
        return text

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _repair_json(content: str) -> str:
    text = content.strip()
    text = text.replace("\ufeff", "")
    text = _extract_json_object(text)
    text = _remove_trailing_commas(text)
    text = _balance_brackets(text)
    return text


def _remove_trailing_commas(text: str) -> str:
    import re

    return re.sub(r",(\s*[}\]])", r"\1", text)


def _balance_brackets(text: str) -> str:
    stack: list[str] = []
    in_string = False
    escape = False
    for char in text:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]":
            if stack:
                stack.pop()
    closing = {"{": "}", "[": "]"}
    return text + "".join(closing[item] for item in reversed(stack))
