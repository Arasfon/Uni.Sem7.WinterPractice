import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from app.core.config import project_root, settings


def db_path() -> Path:
    return project_root() / settings.db_path


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA busy_timeout = 5000;")


def init_db() -> None:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(p), timeout=30, check_same_thread=False)
    try:
        _apply_pragmas(conn)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processings (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,              -- photo|video|stream
                created_at REAL NOT NULL,
                started_at REAL,
                ended_at REAL,
                source TEXT,
                status TEXT NOT NULL,            -- running|ok|error|stopped
                params_json TEXT,
                result_json TEXT,
                error TEXT
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS timeline_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                processing_id TEXT NOT NULL,
                t REAL NOT NULL,
                count INTEGER NOT NULL,
                created_at REAL NOT NULL,
                meta_json TEXT,
                FOREIGN KEY(processing_id) REFERENCES processings(id) ON DELETE CASCADE
            );
            """
        )

        conn.execute("CREATE INDEX IF NOT EXISTS idx_processings_created_at ON processings(created_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_timeline_processing_t ON timeline_points(processing_id, t);")

        conn.commit()
    finally:
        conn.close()


def _now() -> float:
    return time.time()


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


@dataclass
class HistorySession:

    conn: sqlite3.Connection

    @classmethod
    def open(cls) -> "HistorySession":
        p = db_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(p), timeout=30, check_same_thread=False)
        _apply_pragmas(conn)
        return cls(conn=conn)

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def create_processing(
        self,
        *,
        pid: str,
        kind: str,
        source: Optional[str],
        params: dict[str, Any],
        started_at: Optional[float] = None,
    ) -> None:
        ts = _now()
        self.conn.execute(
            """
            INSERT INTO processings
                (id, kind, created_at, started_at, source, status, params_json)
            VALUES
                (?,  ?,   ?,         ?,         ?,      ?,      ?);
            """,
            (pid, kind, ts, started_at if started_at is not None else ts, source, "running", _dumps(params)),
        )
        self.conn.commit()

    def add_timeline_points(
        self,
        *,
        pid: str,
        points: Iterable[tuple[float, int, Optional[dict[str, Any]]]],
    ) -> None:
        ts = _now()
        rows = [(pid, float(t), int(c), ts, _dumps(m) if m else None) for (t, c, m) in points]
        if not rows:
            return
        self.conn.executemany(
            """
            INSERT INTO timeline_points (processing_id, t, count, created_at, meta_json)
            VALUES (?, ?, ?, ?, ?);
            """,
            rows,
        )
        self.conn.commit()

    def finish_processing(
        self,
        *,
        pid: str,
        status: str,
        result: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        avg_count = 0.0
        max_count = 0
        samples = 0

        row = self.conn.execute(
            "SELECT AVG(count), MAX(count), COUNT(*) FROM timeline_points WHERE processing_id = ?",
            (pid,),
        ).fetchone()
        if row:
            avg_count = float(row[0]) if row[0] is not None else 0.0
            max_count = int(row[1]) if row[1] is not None else 0
            samples = int(row[2]) if row[2] is not None else 0

        if result is not None:
            result["samples"] = samples
            result["avg_count"] = avg_count
            result["max_count"] = max_count

        self.conn.execute(
            """
            UPDATE processings
            SET ended_at = ?, status = ?, result_json = ?, error = ?
            WHERE id = ?;
            """,
            (_now(), status, _dumps(result) if result else None, error, pid),
        )
        self.conn.commit()
