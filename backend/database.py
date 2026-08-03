from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.config import DATA_DIR


DB_PATH = DATA_DIR / "research_assistant.sqlite3"


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def migrate(path: Path = DB_PATH) -> None:
    with connect(path) as db:
        db.executescript(
            """
            create table if not exists saved_reports (
              id integer primary key autoincrement,
              created_at text default current_timestamp,
              request_text text not null,
              report_json text not null
            );
            """
        )
