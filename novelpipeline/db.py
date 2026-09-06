from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .models import WorkCandidate


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  discovered_count INTEGER NOT NULL DEFAULT 0,
  processed_count INTEGER NOT NULL DEFAULT 0,
  error TEXT
);

CREATE TABLE IF NOT EXISTS works (
  site TEXT NOT NULL,
  work_id TEXT NOT NULL,
  url TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  author TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  episode_count INTEGER NOT NULL DEFAULT 0,
  source_query TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'DISCOVERED',
  first_seen_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_error TEXT,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (site, work_id)
);

CREATE TABLE IF NOT EXISTS episodes (
  site TEXT NOT NULL,
  work_id TEXT NOT NULL,
  number INTEGER NOT NULL,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  source_sha256 TEXT NOT NULL,
  source_path TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (site, work_id, number),
  FOREIGN KEY (site, work_id) REFERENCES works(site, work_id)
);

CREATE TABLE IF NOT EXISTS translation_chunks (
  site TEXT NOT NULL,
  work_id TEXT NOT NULL,
  chunk_no INTEGER NOT NULL,
  source_sha256 TEXT NOT NULL,
  source_path TEXT NOT NULL,
  translation_path TEXT,
  status TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_error TEXT,
  PRIMARY KEY (site, work_id, chunk_no),
  FOREIGN KEY (site, work_id) REFERENCES works(site, work_id)
);
"""


class StateDB:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def start_run(self) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO runs(started_at,status) VALUES (?,?)",
                (utcnow(), "RUNNING"),
            )
            return int(cur.lastrowid)

    def finish_run(self, run_id: int, *, status: str, discovered: int, processed: int, error: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE runs SET finished_at=?,status=?,discovered_count=?,processed_count=?,error=? WHERE id=?",
                (utcnow(), status, discovered, processed, error, run_id),
            )

    def upsert_candidate(self, candidate: WorkCandidate) -> bool:
        now = utcnow()
        with self.connect() as conn:
            old = conn.execute(
                "SELECT 1 FROM works WHERE site=? AND work_id=?",
                (candidate.site, candidate.work_id),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO works(site,work_id,url,title,author,summary,episode_count,source_query,status,first_seen_at,updated_at,metadata_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(site,work_id) DO UPDATE SET
                  url=excluded.url,
                  title=CASE WHEN excluded.title<>'' THEN excluded.title ELSE works.title END,
                  author=CASE WHEN excluded.author<>'' THEN excluded.author ELSE works.author END,
                  summary=CASE WHEN excluded.summary<>'' THEN excluded.summary ELSE works.summary END,
                  episode_count=MAX(works.episode_count, excluded.episode_count),
                  source_query=CASE WHEN excluded.source_query<>'' THEN excluded.source_query ELSE works.source_query END,
                  updated_at=excluded.updated_at,
                  metadata_json=CASE WHEN excluded.metadata_json<>'{}' THEN excluded.metadata_json ELSE works.metadata_json END
                """,
                (
                    candidate.site,
                    candidate.work_id,
                    candidate.url,
                    candidate.title,
                    candidate.author,
                    candidate.summary,
                    candidate.episode_count,
                    candidate.source_query,
                    "DISCOVERED",
                    now,
                    now,
                    json.dumps(candidate.metadata, ensure_ascii=False),
                ),
            )
            return old is None

    def update_work(self, site: str, work_id: str, **fields) -> None:
        allowed = {"title", "author", "summary", "episode_count", "status", "last_error", "metadata_json"}
        payload = {k: v for k, v in fields.items() if k in allowed}
        if not payload:
            return
        payload["updated_at"] = utcnow()
        columns = ", ".join(f"{k}=?" for k in payload)
        values = list(payload.values()) + [site, work_id]
        with self.connect() as conn:
            conn.execute(f"UPDATE works SET {columns} WHERE site=? AND work_id=?", values)

    def list_works(self, *, limit: int | None = None):
        sql = "SELECT * FROM works ORDER BY first_seen_at DESC"
        args: tuple = ()
        if limit is not None:
            sql += " LIMIT ?"
            args = (limit,)
        with self.connect() as conn:
            return conn.execute(sql, args).fetchall()

    def list_pending(self, statuses: tuple[str, ...], *, limit: int):
        placeholders = ",".join("?" for _ in statuses)
        sql = f"SELECT * FROM works WHERE status IN ({placeholders}) ORDER BY first_seen_at ASC LIMIT ?"
        with self.connect() as conn:
            return conn.execute(sql, (*statuses, limit)).fetchall()

    def get_work(self, site: str, work_id: str):
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM works WHERE site=? AND work_id=?",
                (site, work_id),
            ).fetchone()

    def upsert_episode(self, *, site: str, work_id: str, number: int, url: str, title: str, source_sha256: str, source_path: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO episodes(site,work_id,number,url,title,source_sha256,source_path,fetched_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(site,work_id,number) DO UPDATE SET
                  url=excluded.url,title=excluded.title,source_sha256=excluded.source_sha256,
                  source_path=excluded.source_path,fetched_at=excluded.fetched_at
                """,
                (site, work_id, number, url, title, source_sha256, source_path, utcnow()),
            )

    def get_episode(self, site: str, work_id: str, number: int):
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM episodes WHERE site=? AND work_id=? AND number=?",
                (site, work_id, number),
            ).fetchone()

    def upsert_chunk(self, *, site: str, work_id: str, chunk_no: int, source_sha256: str, source_path: str, translation_path: str | None, status: str, error: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO translation_chunks(site,work_id,chunk_no,source_sha256,source_path,translation_path,status,updated_at,last_error)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(site,work_id,chunk_no) DO UPDATE SET
                  source_sha256=excluded.source_sha256,source_path=excluded.source_path,
                  translation_path=excluded.translation_path,status=excluded.status,
                  updated_at=excluded.updated_at,last_error=excluded.last_error
                """,
                (site, work_id, chunk_no, source_sha256, source_path, translation_path, status, utcnow(), error),
            )

    def get_chunk(self, site: str, work_id: str, chunk_no: int):
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM translation_chunks WHERE site=? AND work_id=? AND chunk_no=?",
                (site, work_id, chunk_no),
            ).fetchone()
