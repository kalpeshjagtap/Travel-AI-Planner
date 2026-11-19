"""Transport mode comparison labels; no mode is claimed available without provider evidence."""
from typing import Any

MODES=("domestic flight","train","bus","ferry","road transfer")

def compare_transfer_options(origin: str, destination: str) -> list[dict[str, Any]]:
    """Return candidate modes requiring live/user verification, never schedules or fares."""
    if not origin.strip() or not destination.strip():
        return []
    return [{"mode":mode,"from":origin,"to":destination,"availability":"unverified",
             "duration":"unavailable","fare":"unavailable"} for mode in MODES]
