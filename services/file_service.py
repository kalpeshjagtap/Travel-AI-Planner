"""JSON-based local persistence service."""

import json
import logging
import os
from pathlib import Path
import re
import tempfile
from datetime import datetime, timezone
from typing import Any

from config.settings import get_settings

logger = logging.getLogger(__name__)


class FileService:
    """Reads and writes application records as JSON files."""

    def __init__(self, data_directory: str | None = None) -> None:
        self.data_directory = Path(data_directory or get_settings().data_directory)
        self.trips_directory = self.data_directory / "trips"
        self.trips_directory.mkdir(parents=True, exist_ok=True)
        self.preferences_path = self.data_directory / "user_preferences.json"

    def save_trip(self, trip_id: str, payload: dict[str, Any]) -> Path:
        """Write one trip record as UTF-8 JSON."""
        self._validate_trip_id(trip_id)
        path = self.trips_directory / f"{trip_id}.json"
        clean = self._without_secrets(payload)
        clean.setdefault("trip_id", trip_id)
        clean.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        clean["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._atomic_json_write(path, clean)
        return path

    def load_trip(self, trip_id: str) -> dict[str, Any]:
        """Load a trip record by identifier."""
        self._validate_trip_id(trip_id)
        path = self.trips_directory / f"{trip_id}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Trip record must contain a JSON object.")
            return data
        except FileNotFoundError:
            raise FileNotFoundError(f"Saved trip '{trip_id}' does not exist.")
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            logger.exception("Saved trip is corrupted: %s", path)
            raise ValueError(f"Saved trip '{trip_id}' is corrupted and could not be loaded.") from exc

    def update_trip(self, trip_id: str, updates: dict[str, Any]) -> Path:
        """Merge fields into an existing trip, preserving its creation timestamp."""
        current = self.load_trip(trip_id)
        current.update(self._without_secrets(updates))
        return self.save_trip(trip_id, current)

    def delete_trip(self, trip_id: str) -> bool:
        """Delete one validated trip JSON record."""
        self._validate_trip_id(trip_id)
        path = self.trips_directory / f"{trip_id}.json"
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False

    def load_preferences(self) -> dict[str, Any]:
        """Read preferences, returning defaults if absent or malformed."""
        try:
            value = json.loads(self.preferences_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return self._without_secrets(value)
        except FileNotFoundError:
            return {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.exception("Preferences JSON is corrupted: %s", self.preferences_path)
        return {}

    def save_preferences(self, preferences: dict[str, Any]) -> Path:
        """Persist non-secret user preferences as JSON."""
        self._atomic_json_write(self.preferences_path, self._without_secrets(preferences))
        return self.preferences_path

    def list_trips(self) -> list[str]:
        """Return saved trip identifiers in stable order."""
        return sorted(path.stem for path in self.trips_directory.glob("*.json") if path.is_file())

    @staticmethod
    def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp") as handle:
                temp_name = handle.name
                json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)

    @classmethod
    def _without_secrets(cls, value: Any) -> Any:
        """Drop credential-bearing keys recursively before JSON persistence."""
        secret_names = {"api_key", "apikey", "access_token", "refresh_token", "client_secret", "password", "oauth_secret", "credentials"}
        if isinstance(value, dict):
            return {k: cls._without_secrets(v) for k, v in value.items() if str(k).casefold() not in secret_names and not str(k).casefold().endswith("_secret")}
        if isinstance(value, list):
            return [cls._without_secrets(item) for item in value]
        return value

    @staticmethod
    def _validate_trip_id(trip_id: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", trip_id):
            raise ValueError("Trip identifier may contain only letters, numbers, dashes, and underscores.")
