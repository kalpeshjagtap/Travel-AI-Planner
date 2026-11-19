"""Small JSON HTTP cache and cross-process rate limiter; no database required."""

import hashlib
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


@contextmanager
def _file_lock(path: Path, timeout: float = 10.0) -> Iterator[None]:
    """Acquire a cross-process lock using only Python's standard library."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        deadline = time.monotonic() + timeout
        locked = False
        if os.name == "nt":
            import msvcrt

            while time.monotonic() < deadline:
                try:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except OSError:
                    time.sleep(0.05)
            def unlock() -> None:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            while time.monotonic() < deadline:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except BlockingIOError:
                    time.sleep(0.05)
            unlock = lambda: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        if not locked:
            raise TimeoutError(f"Timed out acquiring local provider lock: {path.name}")
        try:
            yield
        finally:
            unlock()


class JsonProviderCache:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(namespace: str, value: Any) -> str:
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        return f"{namespace}-{hashlib.sha256(encoded).hexdigest()}"

    def get(self, key: str, *, now: float | None = None) -> Any | None:
        path = self.directory / f"{key}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("expires_at", 0) <= (now or time.time()):
                return None
            return record.get("value")
        except (OSError, json.JSONDecodeError, AttributeError):
            return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        path = self.directory / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with _file_lock(Path(str(path) + ".lock"), timeout=10):
            descriptor, temporary = tempfile.mkstemp(prefix=".provider-", suffix=".tmp", dir=path.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                    json.dump({"expires_at": time.time() + ttl_seconds, "value": value}, stream, ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    def wait_for_interval(self, name: str, interval_seconds: float) -> None:
        """Persist last-request time so rate limiting also covers MCP subprocesses."""
        path = self.directory / f"{name}.rate.json"
        with _file_lock(Path(str(path) + ".lock"), timeout=30):
            try:
                last = float(json.loads(path.read_text(encoding="utf-8")).get("last_request", 0))
            except (OSError, ValueError, json.JSONDecodeError, AttributeError):
                last = 0.0
            delay = interval_seconds - (time.time() - last)
            if delay > 0:
                time.sleep(delay)
            path.write_text(json.dumps({"last_request": time.time()}), encoding="utf-8")


class DailyRequestBudget:
    """Persistent best-effort local quota guard for free-tier providers."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def consume(self, name: str, *, limit: int, amount: int = 1) -> None:
        from datetime import UTC, datetime

        path = self.directory / f"{name}.budget.json"
        with _file_lock(Path(str(path) + ".lock"), timeout=10):
            today = datetime.now(UTC).date().isoformat()
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                record = {}
            used = int(record.get("used", 0)) if record.get("date") == today else 0
            if used + amount > limit:
                raise RuntimeError(f"{name} local daily safety cap reached ({limit}); no provider request was sent.")
            path.write_text(json.dumps({"date": today, "used": used + amount}), encoding="utf-8")
