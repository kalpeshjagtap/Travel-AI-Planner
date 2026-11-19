"""MCP filesystem tools restricted to the local travel-document directory."""

import base64
import logging
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from config.settings import get_settings

logger = logging.getLogger(__name__)
mcp = FastMCP("travel-filesystem")
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".csv", ".md", ".markdown"}
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,179}$")


def _root() -> Path:
    root = Path(get_settings().travel_documents_directory).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_path(name: str) -> Path:
    candidate_name = Path(name).name
    if candidate_name != name or not SAFE_NAME.fullmatch(name):
        raise ValueError("Use a simple filename without directory components.")
    path = (_root() / name).resolve()
    if path.parent != _root():
        raise ValueError("Path is outside the travel documents directory.")
    return path


@mcp.tool()
def list_files() -> dict:
    """List files in the local travel-document library."""
    files = [
        {"name": path.name, "size_bytes": path.stat().st_size, "extension": path.suffix.lower()}
        for path in sorted(_root().iterdir())
        if path.is_file()
    ]
    return {"directory": str(_root()), "files": files}


@mcp.tool()
def read_file(filename: str, max_chars: int = 30000) -> dict:
    """Read a supported travel document as extracted text, bounded to max_chars."""
    path = _safe_path(filename)
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported document type.")
    if max_chars < 1 or max_chars > 100000:
        raise ValueError("max_chars must be between 1 and 100000.")
    from rag.ingestion import load_documents
    documents = load_documents(path)
    return {"filename": filename, "content": "\n\n".join(doc.page_content for doc in documents)[:max_chars]}


@mcp.tool()
def create_file(filename: str, content: str, overwrite: bool = False) -> dict:
    """Create a UTF-8 text/Markdown/CSV file in the travel-document library."""
    path = _safe_path(filename)
    if path.suffix.lower() not in {".txt", ".md", ".markdown", ".csv"}:
        raise ValueError("New files must use TXT, Markdown, or CSV format.")
    if path.exists() and not overwrite:
        raise FileExistsError(f"{filename} already exists; set overwrite only when intended.")
    path.write_text(content, encoding="utf-8")
    return {"filename": filename, "created": True, "size_bytes": path.stat().st_size}


@mcp.tool()
def search_documents(query: str, limit: int = 20) -> dict:
    """Find literal, case-insensitive text matches in supported travel files."""
    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty.")
    limit = max(1, min(limit, 100))
    matches = []
    from rag.ingestion import load_documents
    for path in sorted(_root().iterdir()):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        try:
            extracted = "\n".join(doc.page_content for doc in load_documents(path))
            for line_number, line in enumerate(extracted.splitlines(), 1):
                if query.casefold() in line.casefold():
                    matches.append({"filename": path.name, "line": line_number, "text": line[:1000]})
                    if len(matches) >= limit:
                        return {"query": query, "matches": matches}
        except OSError:
            logger.exception("Could not search travel document %s", path.name)
    return {"query": query, "matches": matches}


@mcp.tool()
def delete_uploaded_document(filename: str, confirm_delete: bool) -> dict:
    """Delete a local uploaded file only when confirm_delete is explicitly true."""
    if not confirm_delete:
        raise PermissionError("Document deletion requires explicit confirmation.")
    path = _safe_path(filename)
    if not path.is_file():
        return {"filename": filename, "deleted": False, "reason": "not_found"}
    path.unlink()
    return {"filename": filename, "deleted": True}


@mcp.tool()
def manage_uploaded_document(filename: str, content_base64: str) -> dict:
    """Persist a supported uploaded file into the local travel-document library."""
    path = _safe_path(filename)
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}.")
    try:
        content = base64.b64decode(content_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Upload content must be valid base64.") from exc
    if not content:
        raise ValueError("Uploaded document is empty.")
    if len(content) > 25 * 1024 * 1024:
        raise ValueError("Uploaded document exceeds the 25 MiB limit.")
    path.write_bytes(content)
    return {"filename": path.name, "path": str(path), "saved": True, "size_bytes": len(content)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
