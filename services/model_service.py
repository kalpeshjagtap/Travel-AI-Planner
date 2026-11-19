"""Compatibility import for the shared Ollama service."""

from langchain_ollama import ChatOllama

from .ollama_service import get_chat_model


__all__ = ["ChatOllama", "get_chat_model"]
