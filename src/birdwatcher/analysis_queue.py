"""Private durable shadow-analysis jobs, independent of camera ownership."""

import fcntl
import json
import os
import sqlite3
from functools import wraps
from pathlib import Path


class AnalysisError(RuntimeError):
    pass


def safe_path(path):
    if ".." in Path(path).parts:
        raise AnalysisError("Parent traversal is not allowed")
    path = Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise AnalysisError("Symlink paths are not allowed")
    return path


def database_errors(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except sqlite3.Error as exc:
            raise AnalysisError("Analysis database operation failed") from exc

    return wrapped


class AnalysisQueue:
    def __init__(self, analysis_dir, queue_limit=100):
        if type(queue_limit) is not int or not 1 <= queue_limit <= 100:
            raise ValueError("queue_limit must be in [1, 100]")
        self.root = safe_path(analysis_dir)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.queue_limit = queue_limit
        self.db = None
        self.lock = None
        try:
            lockpath = safe_path(self.root / "worker.lock")
            fd = os.open(lockpath, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            os.fchmod(fd, 0o600)
            self.lock = os.fdopen(fd, "a+")
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            path = safe_path(self.root / "analysis.sqlite3")
            for suffix in ("-wal", "-shm", "-journal"):
                safe_path(Path(str(path) + suffix))
            self.max_bytes = 64 * 1024 * 1024
            self._budget()
            self.db = sqlite3.connect(path, timeout=5)
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            tables = self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if version not in (0, 1) or (version == 0 and tables):
                raise AnalysisError("Unsupported analysis schema")
            self.db.execute("PRAGMA user_version=1")
            page_size = self.db.execute("PRAGMA page_size").fetchone()[0]
            self.db.execute(f"PRAGMA max_page_count={(24 * 1024 * 1024) // page_size}")
            self.db.execute("PRAGMA wal_autocheckpoint=32")
            self.db.execute("PRAGMA journal_size_limit=0")
            path.chmod(0o600)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA busy_timeout=5000")
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS jobs (key TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, result TEXT)"
            )
            with self.db:
                self.db.execute(
                    "UPDATE jobs SET state=CASE WHEN attempts < 3 THEN 'pending' ELSE 'failed' END WHERE state='running'"
                )
                exhausted = self.db.execute(
                    "SELECT key,payload FROM jobs WHERE state='failed' AND result IS NULL"
                ).fetchall()
                for row in exhausted:
                    payload = json.loads(row["payload"])
                    frames = payload.get("frames", [])
                    settings = payload.get("settings", {})
                    result = dict(
                        schema_version=1,
                        status="analysis_failed",
                        event_id=payload.get("event_id"),
                        manifest_sha256=payload.get("manifest_sha256"),
                        selected_frame_ids=[f["id"] for f in frames],
                        frames=[
                            dict(
                                frame_id=f["id"],
                                status="analysis_failed",
                                detections=[],
                                error=dict(code="retry_exhausted"),
                            )
                            for f in frames
                        ],
                        model=settings.get("model"),
                        regions=settings.get("regions", []),
                        highest_score=None,
                        partial_errors=False,
                        sampling=dict(
                            method="evenly_spaced",
                            total_frames=payload.get("total_frames"),
                            whole_event_claim=False,
                        ),
                        errors=[dict(code="retry_exhausted")],
                    )
                    self.db.execute(
                        "UPDATE jobs SET result=? WHERE key=?",
                        (json.dumps(result, sort_keys=True), row["key"]),
                    )
        except (OSError, sqlite3.Error) as exc:
            self.close()
            raise AnalysisError("Analysis queue unavailable or worker already running") from exc
        except Exception:
            self.close()
            raise

    def _budget(self, additional=0):
        # Reserve twice each transaction payload plus pages; SQLite DB capped at
        # 24 MiB (4096-byte pages), leaving ample room for WAL/checkpoint copies.
        total = 0
        for name in (
            "analysis.sqlite3",
            "analysis.sqlite3-wal",
            "analysis.sqlite3-shm",
            "analysis.sqlite3-journal",
        ):
            path = safe_path(self.root / name)
            if path.exists():
                total += path.stat().st_size
        if total + additional * 2 + 65536 >= self.max_bytes:
            raise AnalysisError("Analysis storage budget exhausted")

    @database_errors
    def enqueue(self, key, payload):
        encoded = json.dumps(payload, sort_keys=True)
        self._budget(len(encoded.encode()))
        with self.db:
            if self.db.execute("SELECT 1 FROM jobs WHERE key=?", (key,)).fetchone():
                return "duplicate"
            count = self.db.execute(
                "SELECT count(*) FROM jobs WHERE state IN ('pending','running')"
            ).fetchone()[0]
            if count >= self.queue_limit:
                return "deferred"
            self.db.execute(
                "INSERT INTO jobs(key,payload,state) VALUES (?,?,'pending')",
                (key, json.dumps(payload, sort_keys=True)),
            )
        return "enqueued"

    @database_errors
    def claim(self):
        self._budget()
        with self.db:
            row = self.db.execute(
                "SELECT * FROM jobs WHERE state='pending' AND attempts < 3 ORDER BY rowid LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            self.db.execute(
                "UPDATE jobs SET state='running', attempts=attempts+1 WHERE key=?", (row["key"],)
            )
        return dict(key=row["key"], payload=json.loads(row["payload"]))

    @database_errors
    def finish(self, key, result):
        self._budget(len(json.dumps(result).encode()))
        with self.db:
            self.db.execute(
                "UPDATE jobs SET state=?,result=? WHERE key=?",
                (
                    "failed" if result["status"] == "analysis_failed" else "completed",
                    json.dumps(result, sort_keys=True),
                    key,
                ),
            )

    @database_errors
    def result(self, key):
        row = self.db.execute("SELECT result FROM jobs WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None
        if self.lock is not None:
            self.lock.close()
            self.lock = None
