"""Retrieval augmented generation components, imported on demand."""

from importlib import import_module

__all__ = [
    "RAGAnswer",
    "TravelRAGService",
    "TravelVectorStore",
    "ingest_uploaded_file",
    "load_uploaded_document",
]

_EXPORT_MODULES = {
    "RAGAnswer": ".qa",
    "TravelRAGService": ".qa",
    "TravelVectorStore": ".vector_store",
    "ingest_uploaded_file": ".ingestion",
    "load_uploaded_document": ".ingestion",
}


def __getattr__(name: str):
    """Avoid importing Chroma until an application path actually needs it."""
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    return getattr(import_module(module_name, __name__), name)
