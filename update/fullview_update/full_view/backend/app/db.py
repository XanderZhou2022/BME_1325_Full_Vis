from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3


APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
FULL_VIEW_ROOT = BACKEND_DIR.parent
DATA_DIR = FULL_VIEW_ROOT / "backend-data"
DB_PATH = DATA_DIR / "fullview.sqlite"
SCHEMA_PATH = BACKEND_DIR / "db" / "schema.sql"


class Database:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


db = Database()
