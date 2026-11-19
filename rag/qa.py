"""Retrieval-augmented question answering over uploaded travel documents."""

from dataclasses import dataclass
from typing import Any

from langchain_core.prompts import ChatPromptTemplate

from services.ollama_service import OllamaService
from .vector_store import TravelVectorStore


class RAGQuestionAnswerError(RuntimeError):
    """Raised when retrieval or local answer generation fails."""


@dataclass(frozen=True)
class RAGAnswer:
    """Answer text and the uploaded document sources used to prepare it."""

    answer: str
    sources: list[dict[str, Any]]


QUESTION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You answer questions about a traveler's uploaded documents. "
            "Use only the supplied context. If the context does not contain "
            "the answer, say that the uploaded documents do not provide it. "
            "Do not invent prices, dates, policies, or recommendations. "
            "Cite source document names inline when useful.",
        ),
        ("human", "Context:\n{context}\n\nQuestion:\n{question}"),
    ]
)


class TravelRAGService:
    """Coordinates local Chroma retrieval and Ollama answer generation."""

    def __init__(
        self,
        vector_store: TravelVectorStore | None = None,
        ollama: OllamaService | None = None,
    ) -> None:
        self.vector_store = vector_store or TravelVectorStore()
        from services.ollama_service import get_ollama_service
        self.ollama = ollama or get_ollama_service()

    def ask(self, question: str, *, k: int | None = None) -> RAGAnswer:
        """Retrieve matching chunks and answer using the configured local LLM."""
        question = question.strip()
        if not question:
            raise ValueError("Enter a question about your uploaded documents.")

        self.ollama.ensure_ready()
        try:
            matches = self.vector_store.similarity_search_with_score(
                question,
                k=k or self.ollama.settings.rag_retrieval_k,
            )
            context_blocks = []
            sources: list[dict[str, Any]] = []
            seen_sources: set[str] = set()
            context_chars = 0
            max_context_chars = 7000
            for document, distance in matches:
                metadata = document.metadata
                name = metadata.get("document_name", "Uploaded document")
                source_id = str(metadata.get("source_id", metadata.get("source", name)))
                block = f"[Source: {name}]\n{document.page_content[:2200]}"
                if context_chars + len(block) > max_context_chars:
                    break
                context_blocks.append(block)
                context_chars += len(block)
                if source_id not in seen_sources:
                    sources.append(
                        {
                            "document_name": name,
                            "source": metadata.get("source", ""),
                            "file_type": metadata.get("file_type", ""),
                            "distance": float(distance),
                        }
                    )
                    seen_sources.add(source_id)

            context = "\n\n---\n\n".join(context_blocks) or "No matching document passages were found."
            response = (QUESTION_PROMPT | self.ollama.get_chat_model()).invoke(
                {"context": context, "question": question}
            )
            return RAGAnswer(answer=str(response.content), sources=sources)
        except Exception as exc:
            raise RAGQuestionAnswerError(f"Could not answer from uploaded documents: {exc}") from exc
