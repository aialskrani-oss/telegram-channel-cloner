import asyncio
import os
import sys
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
    cmd_start, cmd_set_source, cmd_set_dest,
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


def print_banner():
    logger.info("╔══════════════════════════════════════════╗")
    logger.info("║   🤖  بوت نسخ القنوات — Channel Cloner  ║")
    logger.info("║   النسخة 3.0 | Bot API | مجاني 100٪     ║")
    logger.info("╚══════════════════════════════════════════╝")


def main():
    load_env()
    print_banner()

    try:
        config = Config.from_env()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    db = Database(config.db_path)

    # تعيين القنوات من متغيرات البيئة إذا وُجدت
    if config.source_channel:
        db.set_setting("source_channel", config.source_channel)
        logger.info(f"📡 المصدر من البيئة: {config.source_channel}")
    if config.destination_channel:
        db.set_setting("dest_channel", config.destination_channel)
        logger.info(f"📥 الهدف من البيئة: {config.destination_channel}")

    app = (
        Application.builder()
        .token(config.bot_token)
        .build()
    )

    app.bot_data["db"] = db
    app.bot_data["config"] = config

    # أوامر الخاص
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("setsource", cmd_set_source))
    app.add_handler(CommandHandler("setdest", cmd_set_dest))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("help", cmd_help))

    # الرسائل الواردة من القنوات
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_post))

    src = db.get_setting("source_channel", "غير محدد")
    dst = db.get_setting("dest_channel", "غير محدد")
    logger.info(f"📡 المصدر: {src}")
    logger.info(f"📥 الهدف: {dst}")
    logger.info("🚀 البوت يعمل... اضغط Ctrl+C للإيقاف")

    app.run_polling(allowed_updates=["message", "channel_post"])


if __name__ == "__main__":
    main()
