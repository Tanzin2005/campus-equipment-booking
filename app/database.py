"""SQLite persistence. One connection per operation; no global connection."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def connect(path: Path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS equipment (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                location TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY,
                equipment_id INTEGER NOT NULL REFERENCES equipment(id),
                student_name TEXT NOT NULL,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL,
                CHECK (start_at < end_at)
            );
            CREATE INDEX IF NOT EXISTS booking_time_index
                ON bookings(equipment_id, start_at, end_at);
        """)
        db.executemany(
            "INSERT OR IGNORE INTO equipment VALUES (?, ?, ?)",
            [(1, "Oscilloscope 01", "Electronics Lab"),
             (2, "Arduino Kit 01", "Project Lab"),
             (3, "Projector 01", "Seminar Room")],
        )
