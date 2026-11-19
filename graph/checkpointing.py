"""Filesystem-backed JSON checkpointer for LangGraph conversations."""

import asyncio
import base64
import hashlib
import json
import logging
import os
import tempfile
import threading
from collections.abc import AsyncIterator, Iterator, Sequence
from pathlib import Path
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    WRITES_IDX_MAP,
    get_checkpoint_id,
    writes_sort_key,
)

from config.settings import get_settings

logger = logging.getLogger(__name__)


class JSONFileCheckpointer(BaseCheckpointSaver):
    """Persist LangGraph checkpoints and pending writes as atomic JSON files.

    Data is stored below ``data/checkpoints`` by default. Values are encoded
    with LangGraph's configured serializer, then base64-wrapped in JSON so
    message objects and checkpoint channel values can be restored losslessly.
    """

    def __init__(self, directory: str | Path | None = None, *, serde: Any = None) -> None:
        super().__init__(serde=serde)
        self.directory = Path(directory or get_settings().checkpoint_directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _thread_directory(self, thread_id: str, checkpoint_ns: str) -> Path:
        return self.directory / self._digest(thread_id) / self._digest(checkpoint_ns)

    def _record_path(self, thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> Path:
        return self._thread_directory(thread_id, checkpoint_ns) / f"{self._digest(checkpoint_id)}.json"

    def _encode(self, value: Any) -> dict[str, str]:
        type_tag, data = self.serde.dumps_typed(value)
        return {"type": type_tag, "data": base64.b64encode(data).decode("ascii")}

    def _decode(self, encoded: dict[str, str]) -> Any:
        data = base64.b64decode(encoded["data"].encode("ascii"))
        return self.serde.loads_typed((encoded["type"], data))

    def _read_record(self, path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            logger.exception("Unable to read graph checkpoint file %s", path)
            raise RuntimeError(f"Graph checkpoint is unreadable: {path.name}") from exc

    def _write_record(self, path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(prefix=".checkpoint-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(record, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    @staticmethod
    def _config_values(config: RunnableConfig) -> tuple[str, str, str | None]:
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        if not thread_id:
            raise ValueError("LangGraph checkpointing requires configurable.thread_id.")
        return str(thread_id), str(configurable.get("checkpoint_ns", "")), get_checkpoint_id(config)

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id, checkpoint_ns, checkpoint_id = self._config_values(config)
        directory = self._thread_directory(thread_id, checkpoint_ns)
        if not directory.exists():
            return None
        paths = [self._record_path(thread_id, checkpoint_ns, checkpoint_id)] if checkpoint_id else list(directory.glob("*.json"))
        records = []
        for path in paths:
            if not path.is_file():
                continue
            record = self._read_record(path)
            if record.get("thread_id") == thread_id and record.get("checkpoint_ns", "") == checkpoint_ns:
                records.append(record)
        if not records:
            return None
        record = max(records, key=lambda item: item.get("checkpoint_id", ""))
        return self._to_tuple(record)

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        del new_versions
        thread_id, checkpoint_ns, _ = self._config_values(config)
        checkpoint_id = str(checkpoint["id"])
        parent_id = get_checkpoint_id(config)
        record = {
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": parent_id,
            "checkpoint": self._encode(checkpoint),
            "metadata": self._encode(dict(metadata)),
            "writes": [],
        }
        path = self._record_path(thread_id, checkpoint_ns, checkpoint_id)
        with self._lock:
            if path.exists():
                record["writes"] = self._read_record(path).get("writes", [])
            self._write_record(path, record)
        configurable = dict(config.get("configurable", {}))
        configurable.update(
            {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": checkpoint_id}
        )
        return {**config, "configurable": configurable}

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id, checkpoint_ns, checkpoint_id = self._config_values(config)
        if not checkpoint_id:
            raise ValueError("Pending checkpoint writes require configurable.checkpoint_id.")
        path = self._record_path(thread_id, checkpoint_ns, checkpoint_id)
        with self._lock:
            if not path.exists():
                # Some LangGraph versions can emit late task writes after a
                # checkpoint is superseded. The checkpoint state itself is
                # already persisted by put(); orphan writes are not resumable.
                logger.warning("Ignoring writes for missing/superseded checkpoint %s", checkpoint_id)
                return
            record = self._read_record(path)
            pending = record.setdefault("writes", [])
            existing = {(item["task_id"], item["index"]): index for index, item in enumerate(pending)}
            for sequence_index, (channel, value) in enumerate(writes):
                write_index = WRITES_IDX_MAP.get(channel, sequence_index)
                item_index = (task_id, write_index)
                item = {
                    "task_id": task_id,
                    "task_path": task_path,
                    "index": write_index,
                    "channel": channel,
                    "value": self._encode(value),
                }
                if item_index in existing:
                    pending[existing[item_index]] = item
                else:
                    existing[item_index] = len(pending)
                    pending.append(item)
            self._write_record(path, record)

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        configurable = (config or {}).get("configurable", {})
        thread_filter = configurable.get("thread_id")
        namespace_filter = configurable.get("checkpoint_ns")
        before_id = get_checkpoint_id(before) if before else None
        records: list[dict[str, Any]] = []
        if self.directory.exists():
            for path in self.directory.glob("*/*/*.json"):
                record = self._read_record(path)
                if thread_filter and record.get("thread_id") != thread_filter:
                    continue
                if namespace_filter is not None and record.get("checkpoint_ns", "") != namespace_filter:
                    continue
                if before_id and record.get("checkpoint_id", "") >= before_id:
                    continue
                metadata = self._decode(record["metadata"])
                if filter and any(metadata.get(key) != value for key, value in filter.items()):
                    continue
                records.append(record)
        records.sort(key=lambda item: item.get("checkpoint_id", ""), reverse=True)
        if limit is not None:
            records = records[:limit]
        for record in records:
            yield self._to_tuple(record)

    def _to_tuple(self, record: dict[str, Any]) -> CheckpointTuple:
        checkpoint = self._decode(record["checkpoint"])
        metadata = self._decode(record["metadata"])
        thread_id = record["thread_id"]
        checkpoint_ns = record.get("checkpoint_ns", "")
        checkpoint_id = record["checkpoint_id"]
        configurable = {
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint_id,
        }
        parent_id = record.get("parent_checkpoint_id")
        parent_config = None
        if parent_id:
            parent_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": parent_id,
                }
            }
        saved_writes = record.get("writes", [])
        saved_writes.sort(key=lambda item: writes_sort_key(item.get("task_path", ""), item["task_id"], item["index"]))
        writes = [
            (item["task_id"], item["channel"], self._decode(item["value"]))
            for item in saved_writes
        ]
        return CheckpointTuple(
            config={"configurable": configurable},
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=writes,
        )

    def delete_thread(self, thread_id: str) -> None:
        directory = self.directory / self._digest(thread_id)
        if not directory.exists():
            return
        with self._lock:
            for path in sorted(directory.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            directory.rmdir()

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.get_tuple, config)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return await asyncio.to_thread(self.put, config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        for item in await asyncio.to_thread(lambda: list(self.list(config, filter=filter, before=before, limit=limit))):
            yield item

    async def adelete_thread(self, thread_id: str) -> None:
        await asyncio.to_thread(self.delete_thread, thread_id)


def create_checkpointer(directory: str | Path | None = None) -> JSONFileCheckpointer:
    """Create the default local JSON checkpointer for the travel graph."""
    return JSONFileCheckpointer(directory)
