from __future__ import annotations

from app.config.settings import Settings
from app.translator.base import TranslatorProvider
from app.translator.lmstudio_provider import LMStudioTranslator
from app.translator.ollama_provider import OllamaTranslator
from app.translator.openai_provider import OpenAITranslator


SUPPORTED_PROVIDERS = ("openai", "ollama", "lmstudio")


def create_translator(settings: Settings, provider_name: str | None = None, model: str | None = None) -> TranslatorProvider:
    provider = (provider_name or settings.provider).lower()
    if provider == "openai":
        return OpenAITranslator(
            api_key=settings.openai.api_key,
            model=model or settings.openai.model,
            retry_count=settings.translation.retry_count,
        )
    if provider == "ollama":
        return OllamaTranslator(
            base_url=settings.ollama.base_url,
            model=model or settings.ollama.model,
            retry_count=settings.translation.retry_count,
        )
    if provider == "lmstudio":
        return LMStudioTranslator(
            base_url=settings.lmstudio.base_url,
            model=model or settings.lmstudio.model,
            api_key=settings.lmstudio.api_key,
            retry_count=settings.translation.retry_count,
        )
    supported = ", ".join(SUPPORTED_PROVIDERS)
    raise ValueError(f"Unsupported provider '{provider}'. Supported providers: {supported}.")
