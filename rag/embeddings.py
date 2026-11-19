"""Compatibility import for the shared Ollama embedding service."""

from langchain_ollama import OllamaEmbeddings

from services.ollama_service import get_embeddings


__all__ = ["OllamaEmbeddings", "get_embeddings"]
