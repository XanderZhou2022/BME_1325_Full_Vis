#!/usr/bin/env python3
"""Rebuild the Fullview SQLite database from standardized JSON seed files."""

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
FULL_VIEW_ROOT = BACKEND_DIR.parent
WORKSPACE_ROOT = FULL_VIEW_ROOT.parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from hospital.full_view.backend.app.db import db  # noqa: E402
from hospital.full_view.backend.app.seed import seed_if_empty  # noqa: E402


def main() -> None:
    if db.path.exists():
        db.path.unlink()
    db.initialize()
    with db.transaction() as conn:
        seed_if_empty(conn)
    print(f"Seeded {db.path}")


if __name__ == "__main__":
    main()
