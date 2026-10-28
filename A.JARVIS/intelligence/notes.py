"""Per-user local notes storage shared by command routing and the agent tools."""

from __future__ import annotations

from collections import deque
import hashlib
import re
from pathlib import Path


NOTES_DIRECTORY = Path(__file__).resolve().parents[1] / "user_data" / "notes"
MAX_NOTE_LINES_TO_SCAN = 2000
MAX_NOTE_LINE_CHARS = 1000


def notes_path(username: str) -> Path:
    """Build a stable per-user path without placing raw usernames in file names."""
    username_text = str(username)
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", username_text).strip("_")[:32] or "user"
    suffix = hashlib.sha256(username_text.encode("utf-8")).hexdigest()[:12]
    NOTES_DIRECTORY.mkdir(parents=True, exist_ok=True)
    return NOTES_DIRECTORY / f"{safe_name}-{suffix}.txt"


def read_recent_notes(username: str, limit: int = 5) -> list[str]:
    """Read only the latest bounded note lines for one username."""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_NOTE_LINES_TO_SCAN:
        raise ValueError(f"limit must be between 1 and {MAX_NOTE_LINES_TO_SCAN}.")
    path = notes_path(username)
    try:
        with path.open("r", encoding="utf-8") as notes_file:
            recent_lines = deque(notes_file, maxlen=limit)
    except FileNotFoundError:
        return []
    return [line.strip()[:MAX_NOTE_LINE_CHARS] for line in recent_lines if line.strip()]


def search_personal_notes(username: str, query: str, limit: int = 5) -> list[str]:
    """Find recent note lines containing a case-insensitive phrase."""
    if not isinstance(query, str) or not query.strip():
        raise ValueError("A non-empty search query is required.")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10.")
    matches: list[str] = []
    # Scan a bounded tail to avoid loading a very large notes file into memory.
    for line in reversed(read_recent_notes(username, limit=MAX_NOTE_LINES_TO_SCAN)):
        if query.casefold() in line.casefold():
            matches.append(line)
            if len(matches) >= limit:
                break
    return matches
