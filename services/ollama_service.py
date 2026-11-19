"""Reusable client for local Ollama chat and embedding models.

All model traffic is sent to the configured Ollama base URL. This module does
not configure or fall back to a hosted model provider.
"""

from dataclasses import dataclass
from typing import Any

import httpx
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama, OllamaEmbeddings

from config.settings import Settings, get_settings


class OllamaServiceError(RuntimeError):
    """Base error for local Ollama connection or model failures."""


class OllamaUnavailableError(OllamaServiceError):
    """Raised when the Ollama server cannot be reached."""


class OllamaModelUnavailableError(OllamaServiceError):
    """Raised when a configured model is not installed in Ollama."""


@dataclass(frozen=True)
class OllamaHealth:
    """Result of checking the Ollama server and configured models."""

    available: bool
    base_url: str
    installed_models: tuple[str, ...] = ()
    missing_models: tuple[str, ...] = ()
    error: str | None = None


class OllamaService:
    """Creates LangChain Ollama clients and validates local availability."""

    def __init__(self, settings: Settings | None = None, *, timeout: float = 5.0) -> None:
        self.settings = settings or get_settings()
        self.timeout = timeout
        self._chat_model = None
        self._embeddings = None

    def get_chat_model(self) -> ChatOllama:
        """Create the configured local LangChain chat model."""
        if self._chat_model is None:
            self._chat_model = ChatOllama(
            model=self.settings.ollama_chat_model,
            base_url=self.settings.ollama_base_url.rstrip("/"),
            temperature=0,
            num_predict=self.settings.ollama_num_predict,
            client_kwargs={"timeout": self.settings.ollama_request_timeout},
        )
        return self._chat_model

    def get_embeddings(self) -> OllamaEmbeddings:
        """Create the configured local LangChain embedding model."""
        if self._embeddings is None:
            self._embeddings = OllamaEmbeddings(
            model=self.settings.ollama_embedding_model,
            base_url=self.settings.ollama_base_url.rstrip("/"),
            client_kwargs={"timeout": self.settings.ollama_request_timeout},
        )
        return self._embeddings

    def validate_connection(self, *, require_models: bool = True) -> OllamaHealth:
        """Check the local server and optionally verify both configured models.

        Ollama's local ``/api/tags`` endpoint is used so validation does not
        load models or send prompts. Model names are compared without the
        default ``:latest`` tag when the configured name omits a tag.
        """
        base_url = self.settings.ollama_base_url.rstrip("/")
        try:
            response = httpx.get(f"{base_url}/api/tags", timeout=self.timeout)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            installed = tuple(
                model.get("name", "")
                for model in payload.get("models", [])
                if isinstance(model, dict) and model.get("name")
            )
        except (httpx.HTTPError, ValueError) as exc:
            return OllamaHealth(
                available=False,
                base_url=base_url,
                error=(
                    f"Cannot reach Ollama at {base_url}. Start Ollama and check "
                    f"OLLAMA_BASE_URL. Details: {exc}"
                ),
            )

        missing: tuple[str, ...] = ()
        if require_models:
            configured = (self.settings.ollama_chat_model, self.settings.ollama_embedding_model)
            missing = tuple(
                requested
                for requested in configured
                if not any(self._model_matches(requested, found) for found in installed)
            )
        error = None
        if missing:
            error = (
                "Ollama is running, but these configured models are not installed: "
                + ", ".join(missing)
                + ". Pull them locally with `ollama pull <model>`."
            )
        return OllamaHealth(
            available=True,
            base_url=base_url,
            installed_models=installed,
            missing_models=missing,
            error=error,
        )

    def ensure_ready(self, *, require_models: bool = True) -> OllamaHealth:
        """Validate availability and raise an actionable error on failure."""
        health = self.validate_connection(require_models=require_models)
        if not health.available:
            raise OllamaUnavailableError(health.error or "Ollama is unavailable.")
        if health.missing_models:
            raise OllamaModelUnavailableError(health.error or "A configured model is missing.")
        return health

    def generate(self, prompt: str) -> str:
        """Generate text using the configured local chat model."""
        self.ensure_ready()
        try:
            result = self.get_chat_model().invoke(prompt)
        except Exception as exc:
            raise OllamaServiceError(
                f"Local chat generation failed for {self.settings.ollama_chat_model}: {exc}"
            ) from exc
        return str(result.content)

    def embed_query(self, text: str) -> list[float]:
        """Generate one vector using the configured local embedding model."""
        self.ensure_ready()
        try:
            return self.get_embeddings().embed_query(text)
        except Exception as exc:
            raise OllamaServiceError(
                f"Local embedding failed for {self.settings.ollama_embedding_model}: {exc}"
            ) from exc

    @staticmethod
    def _model_matches(requested: str, installed: str) -> bool:
        """Compare model names while accounting for Ollama's implicit latest tag."""
        requested = requested.strip()
        installed = installed.strip()
        if requested == installed:
            return True
        if ":" not in requested:
            return installed == f"{requested}:latest"
        if ":" not in installed:
            return requested == f"{installed}:latest"
        return False


from functools import lru_cache

@lru_cache(maxsize=1)
def get_ollama_service() -> OllamaService:
    return OllamaService()

_default_service = get_ollama_service()


def get_chat_model() -> BaseChatModel:
    """Compatibility factory used by application agents and services."""
    return _default_service.get_chat_model()


def get_embeddings() -> Embeddings:
    """Compatibility factory used by Chroma and RAG components."""
    return _default_service.get_embeddings()
