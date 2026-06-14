import sqlite3
import os
from typing import Optional
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
                    media_file_id   TEXT,
                    text_hash       TEXT,
                    msg_type        TEXT NOT NULL DEFAULT 'unknown',
                    status          TEXT NOT NULL DEFAULT 'success',
                    copied_at       TEXT NOT NULL DEFAULT (datetime('now')),
                    UNIQUE(source_chat_id, source_msg_id, dest_chat_id)
                );

                CREATE INDEX IF NOT EXISTS idx_msg_id
                    ON copied_messages(source_chat_id, source_msg_id);

                CREATE INDEX IF NOT EXISTS idx_file_id
                    ON copied_messages(media_file_id, dest_chat_id)
                    WHERE media_file_id IS NOT NULL;

                CREATE INDEX IF NOT EXISTS idx_text_hash
                    ON copied_messages(text_hash, dest_chat_id)
                    WHERE text_hash IS NOT NULL;
            """)
        logger.info("✅ قاعدة البيانات جاهزة")

    # ── settings ───────────────────────────────────────────────
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO settings(key,value) VALUES(?,?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    # ── deduplication checks ────────────────────────────────────
    def is_msg_copied(self, source_chat: str, source_msg_id: int, dest_chat: str) -> bool:
        """تحقق من نسخ الرسالة بناءً على رقمها."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM copied_messages"
                " WHERE source_chat_id=? AND source_msg_id=? AND dest_chat_id=?",
                (source_chat, source_msg_id, dest_chat),
            ).fetchone()
            return row is not None

    def is_file_copied(self, file_id: str, dest_chat: str) -> bool:
        """تحقق من نسخ نفس الملف (فيديو/صورة/مستند) بناءً على file_id."""
        if not file_id:
            return False
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM copied_messages"
                " WHERE media_file_id=? AND dest_chat_id=? AND status='success'",
                (file_id, dest_chat),
            ).fetchone()
            return row is not None

    def is_text_copied(self, text_hash: str, dest_chat: str) -> bool:
        """تحقق من نسخ نفس النص بناءً على hash."""
        if not text_hash:
            return False
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM copied_messages"
                " WHERE text_hash=? AND dest_chat_id=? AND status='success'",
                (text_hash, dest_chat),
            ).fetchone()
            return row is not None

    # الدالة القديمة للتوافق مع الأرشيف
    def is_copied(self, source_chat: str, source_msg_id: int, dest_chat: str) -> bool:
        return self.is_msg_copied(source_chat, source_msg_id, dest_chat)

    # ── write ───────────────────────────────────────────────────
    def mark_copied(
        self,
        source_chat: str,
        source_msg_id: int,
        dest_chat: str,
        dest_msg_id: Optional[int],
        media_file_id: Optional[str] = None,
        text_hash: Optional[str] = None,
        msg_type: str = "unknown",
    ):
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO copied_messages
                   (source_chat_id, source_msg_id, dest_chat_id,
                    dest_msg_id, media_file_id, text_hash, msg_type)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT DO NOTHING""",
                (source_chat, source_msg_id, dest_chat,
                 dest_msg_id, media_file_id, text_hash, msg_type),
            )

    # ── stats ───────────────────────────────────────────────────
    def get_stats(self) -> dict:
        with self._conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) as c FROM copied_messages WHERE status='success'"
            ).fetchone()["c"]
            today = conn.execute(
                "SELECT COUNT(*) as c FROM copied_messages"
                " WHERE date(copied_at)=date('now') AND status='success'"
            ).fetchone()["c"]
            by_type = conn.execute(
                "SELECT msg_type, COUNT(*) as c FROM copied_messages"
                " WHERE status='success' GROUP BY msg_type ORDER BY c DESC LIMIT 6"
            ).fetchall()
            return {
                "total": total,
                "today": today,
                "by_type": {r["msg_type"]: r["c"] for r in by_type},
            }
