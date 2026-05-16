from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.config.settings import Settings
from app.translator.factory import SUPPORTED_PROVIDERS
from app.translator.openai_compat import normalize_openai_base_url


@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    model: str
    available: bool
    message: str
    base_url: str = ""
    details: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


async def check_provider_health(
    settings: Settings,
    provider_name: str | None = None,
    model: str | None = None,
    timeout: float = 5.0,
) -> ProviderHealth:
    provider = (provider_name or settings.provider).lower()
    if provider not in SUPPORTED_PROVIDERS:
        return ProviderHealth(
            provider=provider,
            model=model or "",
            available=False,
            message=f"Unsupported provider. Use one of: {', '.join(SUPPORTED_PROVIDERS)}.",
        )
    if provider == "openai":
        return await _check_openai(settings, model, timeout)
    if provider == "ollama":
        return await _check_ollama(settings, model, timeout)
    if provider == "lmstudio":
        return await _check_lmstudio(settings, model, timeout)
    raise AssertionError(f"Unhandled provider: {provider}")


def require_provider_available(health: ProviderHealth) -> None:
    if not health.available:
        raise RuntimeError(health.message)


async def _check_openai(settings: Settings, model: str | None, timeout: float) -> ProviderHealth:
    selected_model = model or settings.openai.model
    if not settings.openai.api_key:
        return ProviderHealth(
            provider="openai",
            model=selected_model,
            available=False,
            message="OpenAI API key is missing. Set OPENAI_API_KEY or config openai.api_key.",
        )
    client = AsyncOpenAI(api_key=settings.openai.api_key)
    try:
        await asyncio.wait_for(client.models.retrieve(selected_model), timeout=timeout)
    except Exception as exc:
        return ProviderHealth(
            provider="openai",
            model=selected_model,
            available=False,
            message=f"OpenAI provider unavailable for model '{selected_model}': {_clean_error(exc)}",
        )
    finally:
        await client.close()
    return ProviderHealth(
        provider="openai",
        model=selected_model,
        available=True,
        message=f"OpenAI provider is available for model '{selected_model}'.",
    )


async def _check_lmstudio(settings: Settings, model: str | None, timeout: float) -> ProviderHealth:
    selected_model = model or settings.lmstudio.model
    configured_base_url = settings.lmstudio.base_url.rstrip("/")
    base_url = normalize_openai_base_url(configured_base_url)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{base_url}/models")
            response.raise_for_status()
        data = response.json()
        model_ids = sorted(
            item.get("id", "")
            for item in data.get("data", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        )
    except Exception as exc:
        hint = ""
        if configured_base_url != base_url:
            hint = f" Configured URL was normalized from {configured_base_url} to {base_url}."
        return ProviderHealth(
            provider="lmstudio",
            model=selected_model,
            available=False,
            base_url=base_url,
            message=f"LM Studio is not reachable at {base_url}/models: {_clean_error(exc)}.{hint}",
            details={"configured_base_url": configured_base_url, "effective_base_url": base_url},
        )
    if selected_model not in model_ids:
        available = ", ".join(model_ids[:8]) or "none"
        return ProviderHealth(
            provider="lmstudio",
            model=selected_model,
            available=False,
            base_url=base_url,
            message=f"LM Studio model '{selected_model}' is not loaded. Available models: {available}.",
            details={
                "configured_base_url": configured_base_url,
                "effective_base_url": base_url,
                "models": model_ids,
            },
        )
    return ProviderHealth(
        provider="lmstudio",
        model=selected_model,
        available=True,
        base_url=base_url,
        message=f"LM Studio provider is available for model '{selected_model}'.",
        details={
            "configured_base_url": configured_base_url,
            "effective_base_url": base_url,
            "models": model_ids,
        },
    )


async def _check_ollama(settings: Settings, model: str | None, timeout: float) -> ProviderHealth:
    selected_model = model or settings.ollama.model
    base_url = settings.ollama.base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{base_url}/api/tags")
            response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return ProviderHealth(
            provider="ollama",
            model=selected_model,
            available=False,
            base_url=base_url,
            message=f"Ollama is not reachable at {base_url}: {_clean_error(exc)}",
        )
    model_names = sorted(
        item.get("name", "")
        for item in data.get("models", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    )
    if not _ollama_model_matches(selected_model, model_names):
        available = ", ".join(model_names[:8]) or "none"
        return ProviderHealth(
            provider="ollama",
            model=selected_model,
            available=False,
            base_url=base_url,
            message=f"Ollama model '{selected_model}' is not installed. Available models: {available}.",
            details={"models": model_names},
        )
    return ProviderHealth(
        provider="ollama",
        model=selected_model,
        available=True,
        base_url=base_url,
        message=f"Ollama provider is available for model '{selected_model}'.",
        details={"models": model_names},
    )


def _ollama_model_matches(selected_model: str, model_names: list[str]) -> bool:
    if selected_model in model_names:
        return True
    if ":" not in selected_model:
        return f"{selected_model}:latest" in model_names
    return False


def _clean_error(exc: Exception) -> str:
    message = str(exc).strip()
    if not message:
        message = exc.__class__.__name__
    return message.replace("\n", " ")[:500]
