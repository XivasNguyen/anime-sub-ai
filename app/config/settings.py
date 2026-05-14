from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _resolve_env(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("env:"):
        return os.getenv(value[4:], "")
    if isinstance(value, dict):
        return {key: _resolve_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_env(item) for item in value]
    return value


def _non_empty(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return default


@dataclass
class OpenAISettings:
    api_key: str = ""
    model: str = "gpt-5"


@dataclass
class OllamaSettings:
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5:14b"


@dataclass
class LMStudioSettings:
    base_url: str = "http://localhost:1234/v1"
    model: str = "local-model"
    api_key: str = "lm-studio"


@dataclass
class TranslationSettings:
    chunk_size: int = 12
    overlap_lines: int = 2
    max_concurrency: int = 3
    retry_count: int = 3


@dataclass
class MuxSettings:
    set_default_subtitle: bool = True
    subtitle_language: str = "vie"
    subtitle_track_name: str = "Vietnamese AI"


@dataclass
class OutputSettings:
    directory: Path = Path("output")
    temp_directory: Path = Path("temp")


@dataclass
class Settings:
    provider: str = "openai"
    openai: OpenAISettings = field(default_factory=OpenAISettings)
    ollama: OllamaSettings = field(default_factory=OllamaSettings)
    lmstudio: LMStudioSettings = field(default_factory=LMStudioSettings)
    translation: TranslationSettings = field(default_factory=TranslationSettings)
    mux: MuxSettings = field(default_factory=MuxSettings)
    output: OutputSettings = field(default_factory=OutputSettings)


def load_settings(path: Path | None = None) -> Settings:
    data: dict[str, Any] = {}
    config_path = path or Path("config.yaml")
    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"Config file must contain a YAML mapping: {config_path}")
            data = _resolve_env(loaded)

    openai_data = data.get("openai", {})
    ollama_data = data.get("ollama", {})
    lmstudio_data = data.get("lmstudio", {})
    translation_data = data.get("translation", {})
    mux_data = data.get("mux", {})
    output_data = data.get("output", {})

    return Settings(
        provider=data.get("provider", "openai"),
        openai=OpenAISettings(
            api_key=openai_data.get("api_key", os.getenv("OPENAI_API_KEY", "")),
            model=openai_data.get("model", "gpt-5"),
        ),
        ollama=OllamaSettings(
            base_url=_non_empty(ollama_data.get("base_url"), os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")),
            model=_non_empty(ollama_data.get("model"), os.getenv("OLLAMA_MODEL", "qwen2.5:14b")),
        ),
        lmstudio=LMStudioSettings(
            base_url=_non_empty(
                lmstudio_data.get("base_url"),
                os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1"),
            ),
            model=_non_empty(lmstudio_data.get("model"), os.getenv("LMSTUDIO_MODEL", "local-model")),
            api_key=_non_empty(lmstudio_data.get("api_key"), os.getenv("LMSTUDIO_API_KEY", "lm-studio")),
        ),
        translation=TranslationSettings(
            chunk_size=int(translation_data.get("chunk_size", 12)),
            overlap_lines=int(translation_data.get("overlap_lines", 2)),
            max_concurrency=int(translation_data.get("max_concurrency", 3)),
            retry_count=int(translation_data.get("retry_count", 3)),
        ),
        mux=MuxSettings(
            set_default_subtitle=bool(mux_data.get("set_default_subtitle", True)),
            subtitle_language=mux_data.get("subtitle_language", "vie"),
            subtitle_track_name=mux_data.get("subtitle_track_name", "Vietnamese AI"),
        ),
        output=OutputSettings(
            directory=Path(output_data.get("directory", "output")),
            temp_directory=Path(output_data.get("temp_directory", "temp")),
        ),
    )
