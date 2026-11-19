"""Agent for uploaded-document listings and JSON travel-record operations."""

import logging
import re
import base64
from typing import Any

from graph.state import TravelPlanState
from rag.ingestion import DocumentIndexingError, DocumentIngestionError, ingest_uploaded_file
from rag.vector_store import TravelVectorStore
from services.file_service import FileService
from services.mcp_client import MCPToolRegistry
from .base import BaseAgent

logger = logging.getLogger(__name__)
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


class FileAgent(BaseAgent):
    """Lists indexed sources and saves/loads JSON trip records."""

    name = "file"

    def __init__(self, file_service: FileService | None = None, vector_store: TravelVectorStore | None = None, mcp: MCPToolRegistry | None = None) -> None:
        self.file_service = file_service or FileService()
        self.vector_store = vector_store or TravelVectorStore()
        self.mcp = mcp or MCPToolRegistry()

    def run(self, state: TravelPlanState) -> dict[str, Any]:
        request = state["request"]
        action = request.get("file_action", "").strip().lower()
        logger.info("File agent action %s for trip %s", action, state["trip_id"])
        if action in {"list_sources", "list_documents"}:
            result = {"action": action, **self.mcp.call_tool("filesystem", "list_files", {})}
            result["indexed_sources"] = self.vector_store.list_sources()
        elif action == "ingest_uploads":
            uploads = request.get("uploaded_files", [])
            if not uploads:
                raise ValueError("No uploaded files were included in this file operation.")
            results = []
            for upload in uploads:
                filename = str(upload.get("filename", ""))
                try:
                    content = upload.get("content", b"")
                    if isinstance(content, str):
                        content = content.encode("utf-8")
                    stored = self.mcp.call_tool(
                        "filesystem", "manage_uploaded_document",
                        {"filename": filename, "content_base64": base64.b64encode(content).decode("ascii")},
                    )
                    chunks = ingest_uploaded_file(filename, content, self.vector_store)
                    results.append({**stored, "indexed": True, "chunks": chunks})
                except (DocumentIngestionError, DocumentIndexingError) as exc:
                    results.append({"filename": filename, "indexed": False, "error": str(exc)})
            result = {"action": action, "files": results}
        elif action == "delete_source":
            source_id = request.get("file_source_id", "")
            if not source_id:
                raise ValueError("A source identifier is required to delete indexed document chunks.")
            result = {
                "action": action,
                "deleted_chunks": self.vector_store.delete_source(source_id),
                "source_id": source_id,
            }
        elif action == "list_trips":
            result = {"action": action, "trip_ids": self.file_service.list_trips()}
        elif action in {"save_trip", "save_plan"}:
            # Persist a JSON-safe user-facing snapshot, never LangChain message objects.
            existing = {}
            try:
                existing = self.file_service.load_trip(state["trip_id"])
            except FileNotFoundError:
                pass
            snapshot = request.get("file_action_payload") or {}
            path = self.file_service.save_trip(state["trip_id"], {**existing, **snapshot,
                "trip_id": state["trip_id"], "request": dict(request),
                "itinerary": snapshot.get("itinerary", state.get("itinerary", {})),
                "agent_results": snapshot.get("agent_results", state.get("agent_results", {})),
                "saved_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            })
            result = {"action": action, "saved": True, "path": str(path)}
        elif action == "update_trip":
            trip_id = str(request.get("file_trip_id", state["trip_id"]))
            result = {"action": action, "updated": True, "path": str(self.file_service.update_trip(trip_id, request.get("file_action_payload", {})))}
        elif action == "delete_trip":
            trip_id = str(request.get("file_trip_id", state["trip_id"]))
            result = {"action": action, "deleted": self.file_service.delete_trip(trip_id), "trip_id": trip_id}
        elif action == "load_trip":
            trip_id = str(request.get("file_trip_id", state["trip_id"]))
            if not SAFE_ID.fullmatch(trip_id):
                raise ValueError("Trip identifier may contain only letters, numbers, dashes, and underscores.")
            result = {"action": action, "trip": self.file_service.load_trip(trip_id)}
        elif action == "read_document":
            result = {"action": action, **self.mcp.call_tool("filesystem", "read_file", {"filename": request.get("filename", "")})}
        elif action == "create_document":
            result = {"action": action, **self.mcp.call_tool("filesystem", "create_file", {
                "filename": request.get("filename", ""), "content": request.get("file_content", ""),
                "overwrite": bool(request.get("overwrite_file", False)),
            })}
        elif action == "search_documents":
            result = {"action": action, **self.mcp.call_tool("filesystem", "search_documents", {
                "query": request.get("document_search", ""),
            })}
        elif action == "delete_document":
            result = {"action": action, **self.mcp.call_tool("filesystem", "delete_uploaded_document", {
                "filename": request.get("filename", ""),
                "confirm_delete": bool(request.get("confirm_file_delete", False)),
            })}
        else:
            raise ValueError(
                "file_action must be list_sources, list_documents, ingest_uploads, delete_source, "
                "list_trips, save_trip, save_plan, update_trip, delete_trip, load_trip, read_document, create_document, search_documents, or delete_document."
            )
        return {"agent_results": {self.name: result}}
