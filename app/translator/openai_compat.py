from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def normalize_openai_base_url(base_url: str) -> str:
    """Return an OpenAI-compatible base URL ending in /v1."""
    cleaned = base_url.strip().rstrip("/")
    if not cleaned:
        return ""
    parts = urlsplit(cleaned)
    path = parts.path.rstrip("/")
    if path == "/v1" or path.endswith("/v1"):
        return cleaned
    normalized_path = f"{path}/v1" if path else "/v1"
    return urlunsplit((parts.scheme, parts.netloc, normalized_path, "", ""))
