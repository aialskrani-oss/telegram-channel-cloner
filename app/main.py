import asyncio
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from app.config import Config
from app.database import Database
from app.logger import logger
from app.handlers import (
    cmd_start, cmd_chatid,
    cmd_add_source, cmd_remove_source, cmd_list_sources,
    cmd_set_source_me, cmd_set_dest, cmd_set_dest_me,
    cmd_set_filter, cmd_clear_filter,
    cmd_copy_archive, cmd_stop_archive,
    cmd_status, cmd_stats, cmd_help,
    handle_channel_post,
)


def load_env():
    env = Path(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def start_health_server(port: int):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("🤖 يعمل\n".encode())
        def log_message(self, *a): pass
    threading.Thread(
        target=HTTPServer(("0.0.0.0", port), Handler).serve_forever,
        daemon=True,
    ).start()
    logger.info(f"🌐 Health server :{port}")


def main():
    load_env()
    logger.info("╔══════════════════════════════════════════════╗")
    logger.info("║  🤖  بوت نسخ القنوات v4.0 — متعدد المصادر  ║")
    logger.info("╚══════════════════════════════════════════════╝")

    start_health_server(int(os.getenv("PORT", "10000")))

    try:
        config = Config.from_env()
    except ValueError as e:
        logger.error(str(e)); sys.exit(1)

    db = Database(config.db_path)

    # بيانات البيئة الاختيارية
    if config.source_channel:
        db.add_source_channel(config.source_channel)
    if config.destination_channel:
        db.set_setting("dest_channel", config.destination_channel)

    app = Application.builder().token(config.bot_token).build()
    app.bot_data.update({"db": db, "config": config, "archive_running": False})

    ch = filters.ChatType.CHANNEL

    # ── أوامر الخاص ──────────────────────────────────────
    app.add_handler(CommandHandler("start",         cmd_start))
    app.add_handler(CommandHandler("help",          cmd_help))
    app.add_handler(CommandHandler("chatid",        cmd_chatid))
    app.add_handler(CommandHandler("addsource",     cmd_add_source))
    app.add_handler(CommandHandler("removesource",  cmd_remove_source))
    app.add_handler(CommandHandler("listsources",   cmd_list_sources))
    app.add_handler(CommandHandler("setdest",       cmd_set_dest))
    app.add_handler(CommandHandler("setfilter",     cmd_set_filter))
    app.add_handler(CommandHandler("clearfilter",   cmd_clear_filter))
    app.add_handler(CommandHandler("copyarchive",   cmd_copy_archive))
    app.add_handler(CommandHandler("stoparchive",   cmd_stop_archive))
    app.add_handler(CommandHandler("status",        cmd_status))
    app.add_handler(CommandHandler("stats",         cmd_stats))

    # ── أوامر داخل القنوات ───────────────────────────────
    app.add_handler(CommandHandler("setsourceme",   cmd_set_source_me, filters=ch))
    app.add_handler(CommandHandler("setdestme",     cmd_set_dest_me,   filters=ch))
    app.add_handler(CommandHandler("chatid",        cmd_chatid,        filters=ch))

    # ── رسائل القنوات ────────────────────────────────────
    app.add_handler(MessageHandler(ch, handle_channel_post))

    sources = db.get_source_channels()
    logger.info(f"📡 المصادر: {sources or 'لا توجد'}")
    logger.info(f"📥 الهدف: {db.get_dest_channel() or 'غير محدد'}")
    logger.info(f"🎚 الفلتر: {db.get_filter() or 'الكل'}")
    logger.info("🚀 البوت يعمل...")

    app.run_polling(
        allowed_updates=["message", "channel_post"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
