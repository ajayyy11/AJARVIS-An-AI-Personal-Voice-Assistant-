"""Explicit, operator-triggered AJARVIS cloud database migration/verification."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply or verify the AJARVIS cloud PostgreSQL schema."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply idempotent CREATE/ALTER statements to the configured cloud database.",
    )
    mode.add_argument(
        "--verify",
        action="store_true",
        help="Check required tables and columns without changing the database.",
    )
    args = parser.parse_args()

    try:
        from cloud_app import ensure_cloud_schema, verify_cloud_schema

        if args.apply:
            ensure_cloud_schema()
            print("AJARVIS cloud schema migration completed.")
        else:
            verify_cloud_schema()
            print("AJARVIS cloud schema verification passed; no changes were made.")
    except Exception as exc:
        print(
            "Cloud database operation failed. Check DATABASE_URL, connectivity, "
            "and database permissions. No credentials were printed."
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
