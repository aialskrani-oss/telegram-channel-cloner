import sqlite3
import os
from contextlib import contextmanager
from typing import Optional, Tuple
from app.logger import logger


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS copied_messages (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_chat_id  TEXT NOT NULL,
                    source_msg_id   INTEGER NOT NULL,
                    dest_chat_id    TEXT NOT NULL,
                    dest_msg_id     INTEGER,
                    status          TEXT NOT NULL DEFAULT 'success',
                    copied_at       TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(source_chat_id, source_msg_id, dest_chat_id)
                );

                CREATE INDEX IF NOT EXISTS idx_copied ON copied_messages(source_chat_id, source_msg_id);
            """)
        logger.info("✅ قاعدة البيانات جاهزة")

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def is_copied(self, source_chat: str, source_msg_id: int, dest_chat: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM copied_messages WHERE source_chat_id=? AND source_msg_id=? AND dest_chat_id=?",
                (source_chat, source_msg_id, dest_chat),
            ).fetchone()
            return row is not None

    def mark_copied(self, source_chat: str, source_msg_id: int, dest_chat: str, dest_msg_id: Optional[int]):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO copied_messages(source_chat_id, source_msg_id, dest_chat_id, dest_msg_id)
                   VALUES(?,?,?,?)
                   ON CONFLICT DO NOTHING""",
                (source_chat, source_msg_id, dest_chat, dest_msg_id),
            )

    def get_stats(self) -> dict:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM copied_messages").fetchone()["c"]
            today = conn.execute(
                "SELECT COUNT(*) as c FROM copied_messages WHERE date(copied_at)=date('now')"
            ).fetchone()["c"]
            return {"total": total, "today": today}
