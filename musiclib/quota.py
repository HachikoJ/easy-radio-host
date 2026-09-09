"""Process-safe, persistent rolling budget for the shared GD Studio API."""
import math
import os
from pathlib import Path
import sqlite3
import time


class RollingQuota:
    def __init__(self, path, limit=45, window=300):
        self.path = Path(path)
        self.limit = limit
        self.window = window

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            connection.execute("CREATE TABLE IF NOT EXISTS requests (at REAL NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value REAL NOT NULL)")
        except sqlite3.Error:
            connection.close()
            raise
        return connection

    def inspect(self, reserve=False, cooldown=0):
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            state = dict(connection.execute("SELECT key, value FROM state"))
            # A backwards wall-clock adjustment must not grant fresh quota.
            now = max(time.time(), state.get("last_seen", 0))
            connection.execute("INSERT OR REPLACE INTO state VALUES ('last_seen', ?)", (now,))
            connection.execute("DELETE FROM requests WHERE at <= ?", (now - self.window,))
            blocked = max(state.get("blocked_until", 0), now + cooldown if cooldown else 0)
            if cooldown:
                connection.execute("INSERT OR REPLACE INTO state VALUES ('blocked_until', ?)", (blocked,))
            count, oldest = connection.execute("SELECT COUNT(*), MIN(at) FROM requests").fetchone()
            wait = max(0, blocked - now, (oldest + self.window - now) if count >= self.limit else 0)
            allowed = wait <= 0
            if reserve and allowed:
                connection.execute("INSERT INTO requests VALUES (?)", (now,))
                count += 1
            connection.commit()
            return {"status": "ready" if allowed else "limited",
                    "retry_after": math.ceil(wait), "remaining": max(0, self.limit - count)}
        finally:
            connection.close()


def default_quota_path():
    return os.environ.get("GD_QUOTA_DB") or str(
        Path(os.environ.get("STATE_DIRECTORY", "data").split(":")[0]) / "gd-quota.sqlite3")
