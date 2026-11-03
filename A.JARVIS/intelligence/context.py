"""Bounded intent classification and relevance-ranked conversation context.

This module selects safe text context only. It never executes commands or
changes authorization decisions.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

MAX_CONTEXT_ITEMS = 5
MAX_CONTEXT_CHARS = 6000
_FOLLOW_UP_RE = re.compile(
    r"^(?:and\b|also\b|it\b|that\b|this\b|they\b|them\b|those\b|these\b|"
    r"continue\b|go on\b|do that\b|do it\b|repeat that\b|again\b|"
    r"explain more\b|tell me more\b|what about that\b|why is that\b|how about it\b|"
    r"open it\b|run it\b|search it\b|find it\b|summarize that\b|"
    r"what about it\b|why\b|how\b)",
    re.I,
)
_TOKEN_RE = re.compile(r"[a-z0-9]{2,}", re.I)
_STOP_WORDS = {
    "the", "and", "for", "with", "you", "your", "that", "this", "what",
    "how", "why", "can", "could", "would", "should", "please", "tell",
    "about", "from", "have", "has", "are", "was", "were", "into", "then",
    "again", "more", "same", "make", "help", "want", "need",
}


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _tokens(value: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(_normalise(value)) if token not in _STOP_WORDS}


def is_follow_up(command: str) -> bool:
    """Detect short elliptical requests that depend on conversation context."""
    text = _normalise(command)
    return bool(text and _FOLLOW_UP_RE.search(text))


def classify_intent(command: str) -> str:
    """Classify request type deterministically; classification does not execute."""
    text = _normalise(command)
    if not text:
        return "unknown"
    if is_follow_up(text):
        return "follow_up"
    if re.match(
        r"^(?:open|launch|close|lock|shutdown|restart|turn|set|create|delete|save|"
        r"take|find|search|play|pause|mute|unmute|increase|decrease|volume|"
        r"system activate|system deactivate)\b",
        text,
    ):
        return "command"
    if re.search(r"\b(?:search|look up|research|latest|news|find information)\b", text):
        return "search"
    if text.endswith("?") or re.match(
        r"^(?:who|what|when|where|why|how|is|are|am|do|does|did|can|could|"
        r"would|should|will|tell me|explain|describe)\b",
        text,
    ):
        return "question"
    return "conversation"


def select_relevant_history(
    command: str,
    history: Sequence[Mapping[str, str]] | None,
    *,
    limit: int = MAX_CONTEXT_ITEMS,
) -> list[dict[str, str]]:
    """Select relevant exchanges from caller-provided user-scoped history.

    Follow-ups prefer recent turns. New topics rank by lexical relevance and
    recency. Both item count and total characters are bounded.
    """
    if not isinstance(command, str) or not command.strip() or not history:
        return []
    try:
        max_items = max(0, min(int(limit), MAX_CONTEXT_ITEMS))
    except (TypeError, ValueError):
        max_items = MAX_CONTEXT_ITEMS
    if not max_items:
        return []

    rows = []
    for index, item in enumerate(history):
        if not isinstance(item, Mapping):
            continue
        cmd = str(item.get("command", "") or "").strip()
        response = str(item.get("response", "") or "").strip()
        if cmd:
            rows.append({"command": cmd, "response": response, "_index": index})
    if not rows:
        return []

    if is_follow_up(command):
        chosen = rows[-max_items:]
    else:
        query_tokens = _tokens(command)
        ranked = []
        for row in rows:
            overlap = len(query_tokens & _tokens(row["command"] + " " + row["response"]))
            score = overlap * 3 + row["_index"] / max(1, len(rows))
            ranked.append((score, row["_index"], row))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        chosen = [item[2] for item in ranked[:max_items]]
        chosen.sort(key=lambda row: row["_index"])

    output = []
    budget = MAX_CONTEXT_CHARS
    for row in chosen:
        entry = {"command": row["command"], "response": row["response"]}
        size = len(entry["command"]) + len(entry["response"])
        if size > budget:
            if not output and budget:
                entry["command"] = entry["command"][:budget]
                entry["response"] = entry["response"][:max(0, budget - len(entry["command"]))]
                output.append(entry)
            break
        output.append(entry)
        budget -= size
    return output


def build_context_messages(command: str, history: Sequence[Mapping[str, str]] | None):
    """Build Gemini conversation messages ending in the current user turn."""
    messages = []
    for entry in select_relevant_history(command, history):
        messages.append({"role": "user", "parts": [{"text": entry["command"]}]})
        if entry["response"]:
            messages.append({"role": "model", "parts": [{"text": entry["response"]}]})
    messages.append({"role": "user", "parts": [{"text": command}]})
    return messages
