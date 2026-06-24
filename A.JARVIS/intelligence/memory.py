# intelligence/memory.py
# Persistent memory: reads/writes to MySQL, falls back to in-memory list.

from database.db import get_connection

MAX_MEMORY = 50

# In-memory fallback cache (also used to reduce DB reads)
_cache = []


def add_memory(command, response):
    """Save a command+response pair to DB and update local cache."""
    global _cache
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO command_history (command, response) VALUES (%s, %s)",
            (command, response)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print("Memory DB write error:", e)

    # Update local cache too
    _cache.append({"command": command, "response": response})
    if len(_cache) > MAX_MEMORY:
        _cache.pop(0)


def get_recent(n=5):
    """
    Fetch the n most recent entries from DB.
    Falls back to in-memory cache if DB is unavailable.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT command, response FROM command_history ORDER BY id DESC LIMIT %s",
            (n,)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        # Return oldest-first so AI context is chronological
        return [{"command": r[0], "response": r[1]} for r in reversed(rows)]
    except Exception as e:
        print("Memory DB read error:", e)
        return _cache[-n:]


def get_all_recent(n=20):
    """Get last n entries for the dashboard history panel."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT command, response FROM command_history ORDER BY id DESC LIMIT %s",
            (n,)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{"command": r[0], "response": r[1]} for r in rows]
    except Exception as e:
        print("Memory DB read error:", e)
        return list(reversed(_cache[-n:]))