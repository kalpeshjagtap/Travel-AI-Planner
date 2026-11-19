"""ChromaDB vector store wrapper."""

from langchain_chroma import Chroma

from config.settings import Settings, get_settings
from .embeddings import get_embeddings


class TravelVectorStore:
    """Owns the persistent Chroma collection used for travel knowledge."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self.store = Chroma(
            collection_name=settings.chroma_collection_name,
            embedding_function=get_embeddings(),
            persist_directory=settings.chroma_persist_directory,
        )

    def as_retriever(self, *, k: int = 4):
        """Return a LangChain retriever for the configured collection."""
        return self.store.as_retriever(search_kwargs={"k": k})

    def similarity_search_with_score(self, query: str, *, k: int = 4):
        """Return relevant chunks and Chroma distance scores."""
        return self.store.similarity_search_with_score(query, k=k)

    def list_sources(self) -> list[dict[str, str]]:
        """List distinct uploaded document names in the collection."""
        result = self.store.get(include=["metadatas"])
        seen: dict[str, dict[str, str]] = {}
        for metadata in result.get("metadatas", []):
            if not metadata:
                continue
            source_id = str(metadata.get("source_id", metadata.get("source", "unknown")))
            seen[source_id] = {
                "document_name": str(metadata.get("document_name", "Unknown document")),
                "source": str(metadata.get("source", "")),
                "file_type": str(metadata.get("file_type", "")),
                "source_id": source_id,
            }
        return sorted(seen.values(), key=lambda item: item["document_name"].casefold())

    def delete_source(self, source_id: str) -> int:
        """Delete all chunks belonging to one indexed source identifier."""
        existing = self.store.get(where={"source_id": source_id}, include=["metadatas"])
        count = len(existing.get("ids", []))
        if count:
            self.store.delete(where={"source_id": source_id})
        return count
