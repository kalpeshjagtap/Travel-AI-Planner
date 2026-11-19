"""Retrieval and question-answering service functions."""

from langchain_core.documents import Document

from .qa import RAGAnswer, TravelRAGService
from .vector_store import TravelVectorStore


def retrieve_context(query: str, vector_store: TravelVectorStore, *, k: int = 4) -> list[Document]:
    """Retrieve relevant knowledge passages for a travel query."""
    return vector_store.store.similarity_search(query, k=k)


def answer_question(query: str, vector_store: TravelVectorStore | None = None) -> RAGAnswer:
    """Answer a question from indexed documents with source references."""
    return TravelRAGService(vector_store=vector_store).ask(query)
