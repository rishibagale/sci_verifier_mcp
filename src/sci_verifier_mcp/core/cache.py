"""Persistent SQLite caching for literature and REST API requests."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from sci_verifier_mcp.core import config


class SQLiteCache:
    """Thread-safe SQLite persistent cache for HTTP responses."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path or config.CACHE_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), timeout=10.0)

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_cache (
                    cache_key TEXT PRIMARY KEY,
                    endpoint TEXT,
                    data TEXT,
                    created_at REAL
                )
            """)
            conn.commit()

    def get(self, cache_key: str, max_age_seconds: float = 7 * 86400.0) -> Any | None:
        """Retrieve cached JSON object if not expired."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT data, created_at FROM api_cache WHERE cache_key = ?",
                    (cache_key,)
                )
                row = cursor.fetchone()
                if row:
                    data_str, created_at = row
                    if time.time() - created_at < max_age_seconds:
                        return json.loads(data_str)
        except Exception:
            return None
        return None

    def set(self, cache_key: str, endpoint: str, data: Any) -> None:
        """Store JSON object in SQLite cache."""
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO api_cache (cache_key, endpoint, data, created_at) VALUES (?, ?, ?, ?)",
                    (cache_key, endpoint, json.dumps(data), time.time())
                )
                conn.commit()
        except Exception:
            pass


# Global cache instance
cache = SQLiteCache()
