"""SQLite-based audio cache for the TTS API service.

Stores synthesized audio files keyed by a SHA-256 hash of the request
parameters (text + lang + speed + voice_id) so identical requests can be
served instantly from disk.
"""

import hashlib
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Vieneu.API.Cache")

CACHE_DIR = os.getenv("TTS_CACHE_DIR", "storage/audio_cache")
DB_PATH = os.getenv("TTS_DB_PATH", "storage/tts_cache.db")
CLEANUP_DAYS = int(os.getenv("TTS_CLEANUP_DAYS", "30"))


@dataclass
class CacheEntry:
    """A single row from the tts_cache table."""

    id: int
    hash: str
    text: str
    lang: str
    speed: float
    voice_id: str
    file_path: str
    created_at: float
    last_used: float


def _compute_hash(text: str, lang: str, speed: float, voice_id: str) -> str:
    """Return a deterministic SHA-256 hex digest for the given parameters."""
    raw = f"{text}|{lang}|{speed:.4f}|{voice_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TTSCache:
    """Thread-safe SQLite cache manager for synthesized audio files."""

    def __init__(
        self,
        db_path: str = DB_PATH,
        cache_dir: str = CACHE_DIR,
    ) -> None:
        self.db_path = db_path
        self.cache_dir = cache_dir
        self._lock = threading.Lock()

        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)

        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_table()

    def _create_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tts_cache (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                hash       TEXT    UNIQUE NOT NULL,
                text       TEXT    NOT NULL,
                lang       TEXT    NOT NULL,
                speed      REAL    NOT NULL,
                voice_id   TEXT    NOT NULL,
                file_path  TEXT    NOT NULL,
                created_at REAL    NOT NULL,
                last_used  REAL    NOT NULL
            )
            """
        )
        self._conn.commit()

    def lookup(
        self, text: str, lang: str, speed: float, voice_id: str
    ) -> Optional[CacheEntry]:
        """Return the cached entry if both the DB record and physical file exist."""
        h = _compute_hash(text, lang, speed, voice_id)
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM tts_cache WHERE hash = ?", (h,)
            ).fetchone()
            if row is None:
                return None

            entry = CacheEntry(*row)
            if not os.path.isfile(entry.file_path):
                self._conn.execute("DELETE FROM tts_cache WHERE hash = ?", (h,))
                self._conn.commit()
                return None

            self._conn.execute(
                "UPDATE tts_cache SET last_used = ? WHERE hash = ?",
                (time.time(), h),
            )
            self._conn.commit()
            return entry

    def store(
        self,
        text: str,
        lang: str,
        speed: float,
        voice_id: str,
        file_path: str,
    ) -> CacheEntry:
        """Insert or replace a cache entry for the given parameters."""
        h = _compute_hash(text, lang, speed, voice_id)
        now = time.time()

        with self._lock:
            old = self._conn.execute(
                "SELECT file_path FROM tts_cache WHERE hash = ?", (h,)
            ).fetchone()
            if old is not None:
                old_path = old[0]
                if old_path != file_path and os.path.isfile(old_path):
                    try:
                        os.remove(old_path)
                    except OSError:
                        pass
                self._conn.execute(
                    """UPDATE tts_cache
                       SET file_path = ?, created_at = ?, last_used = ?
                       WHERE hash = ?""",
                    (file_path, now, now, h),
                )
            else:
                self._conn.execute(
                    """INSERT INTO tts_cache
                       (hash, text, lang, speed, voice_id, file_path, created_at, last_used)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (h, text, lang, speed, voice_id, file_path, now, now),
                )
            self._conn.commit()

            row = self._conn.execute(
                "SELECT * FROM tts_cache WHERE hash = ?", (h,)
            ).fetchone()
            return CacheEntry(*row)

    def invalidate(
        self, text: str, lang: str, speed: float, voice_id: str
    ) -> None:
        """Remove a cache entry and its physical file."""
        h = _compute_hash(text, lang, speed, voice_id)
        with self._lock:
            row = self._conn.execute(
                "SELECT file_path FROM tts_cache WHERE hash = ?", (h,)
            ).fetchone()
            if row is not None:
                if os.path.isfile(row[0]):
                    try:
                        os.remove(row[0])
                    except OSError:
                        pass
                self._conn.execute("DELETE FROM tts_cache WHERE hash = ?", (h,))
                self._conn.commit()

    def cleanup_old(self, max_age_days: int = CLEANUP_DAYS) -> int:
        """Delete entries (and files) older than *max_age_days*.

        Returns:
            Number of entries removed.
        """
        cutoff = time.time() - max_age_days * 86400
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, file_path FROM tts_cache WHERE last_used < ?",
                (cutoff,),
            ).fetchall()

            for row_id, fpath in rows:
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                    except OSError:
                        pass
                self._conn.execute("DELETE FROM tts_cache WHERE id = ?", (row_id,))

            self._conn.commit()
        if rows:
            logger.info(f"Cache cleanup: removed {len(rows)} stale entries")
        return len(rows)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()
