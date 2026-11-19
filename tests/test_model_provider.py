import sys
from types import ModuleType

import pytest
from pydantic import SecretStr

from config.settings import Settings
from services.ollama_service import OllamaService, OllamaServiceError


def test_gemini_mode_builds_chat_and_embedding_clients_from_configured_secret(monkeypatch):
    calls = {}

    class FakeChat:
        def __init__(self, **kwargs):
            calls["chat"] = kwargs

    class FakeEmbeddings:
        def __init__(self, **kwargs):
            calls["embeddings"] = kwargs

    module = ModuleType("langchain_google_genai")
    module.ChatGoogleGenerativeAI = FakeChat
    module.GoogleGenerativeAIEmbeddings = FakeEmbeddings
    monkeypatch.setitem(sys.modules, "langchain_google_genai", module)

    service = OllamaService(Settings(
        ai_provider="gemini",
        google_api_key=SecretStr("test-key"),
        gemini_chat_model="gemini-test-chat",
        gemini_embedding_model="gemini-test-embed",
    ))
    assert isinstance(service.get_chat_model(), FakeChat)
    assert isinstance(service.get_embeddings(), FakeEmbeddings)
    assert calls["chat"]["model"] == "gemini-test-chat"
    assert calls["embeddings"]["model"] == "gemini-test-embed"
    assert calls["chat"]["google_api_key"] == "test-key"
    assert calls["embeddings"]["google_api_key"] == "test-key"


def test_gemini_mode_fails_clearly_when_api_key_is_missing():
    service = OllamaService(Settings(ai_provider="gemini"))
    health = service.validate_connection()
    assert health.available is False
    assert "GOOGLE_API_KEY" in health.error
    with pytest.raises(OllamaServiceError, match="GOOGLE_API_KEY"):
        service.get_chat_model()
