import sqlite3
import os
from contextlib import contextmanager
from typing import Optional, List, Tuple
from app.logger import logger


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _conn(self):
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_message_id INTEGER NOT NULL,
                    destination_message_id INTEGER,
                    source_channel TEXT NOT NULL,
                    destination_channel TEXT NOT NULL,
                    message_type TEXT NOT NULL DEFAULT 'text',
                    copied_at TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    error_message TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(source_message_id, source_channel, destination_channel)
                );

                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_channel TEXT NOT NULL,
                    destination_channel TEXT NOT NULL,
                    last_processed_id INTEGER NOT NULL DEFAULT 0,
                    last_synced_at TEXT,
                    total_copied INTEGER NOT NULL DEFAULT 0,
                    total_failed INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(source_channel, destination_channel)
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE INDEX IF NOT EXISTS idx_messages_source ON messages(source_message_id, source_channel);
                CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status);
                CREATE INDEX IF NOT EXISTS idx_checkpoints_channels ON checkpoints(source_channel, destination_channel);
            """)
        logger.info("✅ تم تهيئة قاعدة البيانات بنجاح")

    def get_checkpoint(self, source: str, dest: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT last_processed_id FROM checkpoints WHERE source_channel=? AND destination_channel=?",
                (source, dest)
            ).fetchone()
            return row["last_processed_id"] if row else 0

    def update_checkpoint(self, source: str, dest: str, last_id: int, copied: int = 0, failed: int = 0):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO checkpoints (source_channel, destination_channel, last_processed_id, last_synced_at, total_copied, total_failed)
                VALUES (?, ?, ?, datetime('now'), ?, ?)
                ON CONFLICT(source_channel, destination_channel) DO UPDATE SET
                    last_processed_id = excluded.last_processed_id,
                    last_synced_at = excluded.last_synced_at,
                    total_copied = total_copied + excluded.total_copied,
                    total_failed = total_failed + excluded.total_failed
            """, (source, dest, last_id, copied, failed))

    def is_message_copied(self, source_msg_id: int, source: str, dest: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM messages WHERE source_message_id=? AND source_channel=? AND destination_channel=? AND status='success'",
                (source_msg_id, source, dest)
            ).fetchone()
            return row is not None

    def save_message(self, source_id: int, dest_id: Optional[int], source: str, dest: str,
                     msg_type: str, status: str, error: Optional[str] = None):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO messages (source_message_id, destination_message_id, source_channel, destination_channel,
                    message_type, copied_at, status, error_message)
                VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?)
                ON CONFLICT(source_message_id, source_channel, destination_channel) DO UPDATE SET
                    destination_message_id = excluded.destination_message_id,
                    status = excluded.status,
                    error_message = excluded.error_message,
                    copied_at = excluded.copied_at,
                    retry_count = retry_count + 1
            """, (source_id, dest_id, source, dest, msg_type, status, error))

    def get_failed_messages(self, source: str, dest: str, max_retries: int = 5) -> List[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(
                "SELECT * FROM messages WHERE source_channel=? AND destination_channel=? AND status='failed' AND retry_count < ?",
                (source, dest, max_retries)
            ).fetchall()

    def get_stats(self, source: str, dest: str) -> dict:
        with self._conn() as conn:
            checkpoint = conn.execute(
                "SELECT * FROM checkpoints WHERE source_channel=? AND destination_channel=?",
                (source, dest)
            ).fetchone()
            counts = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM messages WHERE source_channel=? AND destination_channel=? GROUP BY status",
                (source, dest)
            ).fetchall()
            stats = {row["status"]: row["cnt"] for row in counts}
            return {
                "last_processed_id": checkpoint["last_processed_id"] if checkpoint else 0,
                "last_synced_at": checkpoint["last_synced_at"] if checkpoint else None,
                "total_copied": checkpoint["total_copied"] if checkpoint else 0,
                "total_failed": checkpoint["total_failed"] if checkpoint else 0,
                "success": stats.get("success", 0),
                "failed": stats.get("failed", 0),
                "pending": stats.get("pending", 0),
            }

    def set_setting(self, key: str, value: str):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """, (key, value))

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default
