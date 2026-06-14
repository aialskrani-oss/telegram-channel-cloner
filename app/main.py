import asyncio
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)
from app.config import Config
from app.database import Database
from app.logger import logger
from app.handlers import (
    cmd_start, cmd_chatid,
    cmd_set_source, cmd_set_dest,
    cmd_set_source_me, cmd_set_dest_me,
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
            self.wfile.write("🤖 البوت يعمل\n".encode())
        def log_message(self, *a): pass

    server = HTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info(f"🌐 خادم الصحة يعمل على البورت {port}")


def print_banner():
    logger.info("╔══════════════════════════════════════════╗")
    logger.info("║   🤖  بوت نسخ القنوات — Channel Cloner  ║")
    logger.info("║   النسخة 3.1 | Bot API | مجاني 100٪     ║")
    logger.info("╚══════════════════════════════════════════╝")


def main():
    load_env()
    print_banner()

    port = int(os.getenv("PORT", "10000"))
    start_health_server(port)

    try:
        config = Config.from_env()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    db = Database(config.db_path)

    if config.source_channel:
        db.set_setting("source_channel", config.source_channel)
        logger.info(f"📡 المصدر: {config.source_channel}")
    if config.destination_channel:
        db.set_setting("dest_channel", config.destination_channel)
        logger.info(f"📥 الهدف: {config.destination_channel}")

    app = Application.builder().token(config.bot_token).build()
    app.bot_data["db"]     = db
    app.bot_data["config"] = config

    # أوامر الخاص
    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("chatid",      cmd_chatid))
    app.add_handler(CommandHandler("setsource",   cmd_set_source))
    app.add_handler(CommandHandler("setdest",     cmd_set_dest))
    app.add_handler(CommandHandler("status",      cmd_status))
    app.add_handler(CommandHandler("stats",       cmd_stats))
    app.add_handler(CommandHandler("help",        cmd_help))

    # أوامر داخل القنوات — تعيين تلقائي
    channel_filter = filters.ChatType.CHANNEL
    app.add_handler(CommandHandler("setsourceme", cmd_set_source_me, filters=channel_filter))
    app.add_handler(CommandHandler("setdestme",   cmd_set_dest_me,   filters=channel_filter))
    app.add_handler(CommandHandler("chatid",      cmd_chatid,        filters=channel_filter))

    # رسائل القنوات العادية
    app.add_handler(MessageHandler(channel_filter, handle_channel_post))

    src = db.get_setting("source_channel", "غير محدد")
    dst = db.get_setting("dest_channel",   "غير محدد")
    logger.info(f"📡 المصدر: {src} | 📥 الهدف: {dst}")
    logger.info("🚀 البوت يعمل...")

    app.run_polling(
        allowed_updates=["message", "channel_post"],
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
