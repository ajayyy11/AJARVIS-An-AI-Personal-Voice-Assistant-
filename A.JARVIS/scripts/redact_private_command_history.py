"""Redact legacy private note and memory commands from AJARVIS command history.

Run from A.JARVIS:
    python scripts/redact_private_command_history.py          # dry run
    python scripts/redact_private_command_history.py --apply  # redact matches

The script never prints command or response contents. It replaces the text of
matched history rows with the same placeholders used for new private commands.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.db import get_connection
from intelligence.memory import (
    PRIVATE_HISTORY_COMMAND,
    PRIVATE_HISTORY_RESPONSE,
    is_sensitive_history_command,
)


def redact_history(
    *,
    apply: bool = False,
    batch_size: int = 500,
    connection_factory: Callable = get_connection,
) -> tuple[int, int]:
    """Return (rows scanned, sensitive rows found); update only when apply=True."""
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 5000:
        raise ValueError("batch_size must be an integer between 1 and 5000")

    connection = cursor = None
    scanned = matched = last_id = 0
    try:
        connection = connection_factory()
        cursor = connection.cursor()
        while True:
            cursor.execute(
                "SELECT id, command FROM command_history "
                "WHERE id > %s ORDER BY id ASC LIMIT %s",
                (last_id, batch_size),
            )
            rows = cursor.fetchall()
            if not rows:
                break

            scanned += len(rows)
            batch_ids = []
            for row in rows:
                row_id, command = row[0], row[1]
                last_id = int(row_id)
                if is_sensitive_history_command(command):
                    batch_ids.append(last_id)

            matched += len(batch_ids)
            if apply and batch_ids:
                for row_id in batch_ids:
                    cursor.execute(
                        "UPDATE command_history SET command = %s, response = %s WHERE id = %s",
                        (PRIVATE_HISTORY_COMMAND, PRIVATE_HISTORY_RESPONSE, row_id),
                    )
                connection.commit()

        return scanned, matched
    except Exception:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        raise
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Redact legacy private AJARVIS command-history records.")
    parser.add_argument("--apply", action="store_true", help="Write redactions. Without this flag, perform a dry run.")
    parser.add_argument("--batch-size", type=int, default=500, help="Rows to scan per query (1–5000; default: 500).")
    args = parser.parse_args()

    try:
        scanned, matched = redact_history(apply=args.apply, batch_size=args.batch_size)
    except Exception:
        print("History cleanup could not complete. Check database connectivity and schema, then retry.")
        return 1

    print(f"Scanned {scanned} history rows; {matched} sensitive rows matched.")
    if args.apply:
        print("Matched rows have been redacted.")
    else:
        print("Dry run only; no database rows were changed. Re-run with --apply to redact the matches.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
