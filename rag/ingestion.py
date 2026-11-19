"""Loading, extracting, chunking, and indexing travel documents."""

from __future__ import annotations

import csv
import hashlib
import io
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config.settings import get_settings
if TYPE_CHECKING:
    from .vector_store import TravelVectorStore

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".md", ".markdown"}


class DocumentIngestionError(ValueError):
    """Base error for unsupported, unreadable, or empty uploads."""


class UnsupportedFileTypeError(DocumentIngestionError):
    """Raised when an upload's extension is not supported."""


class CorruptedDocumentError(DocumentIngestionError):
    """Raised when a supported file cannot be parsed."""


class DocumentIndexingError(RuntimeError):
    """Raised when chunk embeddings cannot be stored in ChromaDB."""


def load_documents(source: Path) -> list[Document]:
    """Load one supported document from disk and extract its text."""
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise CorruptedDocumentError(f"Could not read {source.name}: {exc}") from exc
    return load_uploaded_document(source.name, payload)


def load_uploaded_document(filename: str, payload: bytes) -> list[Document]:
    """Extract text from uploaded bytes into LangChain Documents.

    CSV rows are converted to labeled text records so retrieval preserves
    column names. Each source document records its original filename and
    source label in metadata.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedFileTypeError(f"Unsupported file type {suffix or '(no extension)'}. Supported: {allowed}.")
    if not payload:
        raise CorruptedDocumentError(f"{filename} is empty.")

    try:
        if suffix == ".pdf":
            text = _extract_pdf(payload)
        elif suffix == ".docx":
            text = _extract_docx(payload)
        elif suffix == ".csv":
            text = _extract_csv(payload)
        else:
            text = _decode_text(payload, filename)
    except DocumentIngestionError:
        raise
    except Exception as exc:
        raise CorruptedDocumentError(f"Could not extract text from {filename}: {exc}") from exc

    text = text.strip()
    if not text:
        raise CorruptedDocumentError(f"No readable text was found in {filename}.")

    content_hash = hashlib.sha256(payload).hexdigest()
    source_id = hashlib.sha256(f"{Path(filename).name.casefold()}:{content_hash}".encode("utf-8")).hexdigest()
    metadata = {
        "document_name": Path(filename).name,
        "source": f"upload:{Path(filename).name}",
        "source_id": source_id,
        "file_type": suffix.lstrip("."),
        "uploaded_at": datetime.now(UTC).isoformat(),
    }
    return [Document(page_content=text, metadata=metadata)]


def split_documents(documents: list[Document]) -> list[Document]:
    """Split extracted documents into overlapping, source-aware chunks."""
    settings = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.rag_chunk_size,
        chunk_overlap=settings.rag_chunk_overlap,
        add_start_index=True,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    return splitter.split_documents(documents)


def ingest_documents(documents: list[Document], vector_store: TravelVectorStore) -> int:
    """Split and persist prepared LangChain documents; return chunk count."""
    chunks = split_documents(documents)
    if not chunks:
        raise DocumentIngestionError("The document did not contain text to index.")

    ids = []
    for index, chunk in enumerate(chunks):
        source_id = chunk.metadata.get("source_id", "unknown")
        start_index = chunk.metadata.get("start_index", index)
        chunk_id = hashlib.sha256(f"{source_id}:{start_index}:{index}".encode("utf-8")).hexdigest()
        ids.append(chunk_id)
    try:
        vector_store.store.add_documents(chunks, ids=ids)
    except Exception as exc:
        raise DocumentIndexingError(
            "Could not generate local embeddings or write chunks to ChromaDB. "
            "Check that Ollama is running with the configured embedding model. "
            f"Details: {exc}"
        ) from exc
    return len(chunks)


def ingest_uploaded_file(filename: str, payload: bytes, vector_store: TravelVectorStore) -> int:
    """Load, split, embed, and persist one user-uploaded file."""
    return ingest_documents(load_uploaded_document(filename, payload), vector_store)


def _extract_pdf(payload: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(payload), strict=True)
    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                raise CorruptedDocumentError("Encrypted PDFs are not supported.")
        except Exception as exc:
            if isinstance(exc, CorruptedDocumentError):
                raise
            raise CorruptedDocumentError("Encrypted PDFs are not supported.") from exc
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(payload: bytes) -> str:
    from docx import Document as DocxDocument

    document = DocxDocument(io.BytesIO(payload))
    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            values = [cell.text.strip() for cell in row.cells]
            if any(values):
                parts.append(" | ".join(values))
    return "\n".join(parts)


def _extract_csv(payload: bytes) -> str:
    decoded = _decode_text(payload, "uploaded CSV")
    try:
        rows = list(csv.DictReader(io.StringIO(decoded)))
    except csv.Error as exc:
        raise CorruptedDocumentError(f"Invalid CSV: {exc}") from exc
    if not rows:
        raise CorruptedDocumentError("CSV has no data rows or a readable header.")
    lines = []
    for row_number, row in enumerate(rows, start=1):
        fields = [f"{key}: {value}" for key, value in row.items() if key and value]
        if fields:
            lines.append(f"Row {row_number}. " + "; ".join(fields))
    return "\n".join(lines)


def _decode_text(payload: bytes, filename: str) -> str:
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CorruptedDocumentError(f"{filename} must be UTF-8 encoded text.") from exc
