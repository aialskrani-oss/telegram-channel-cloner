import asyncio
import signal
import sys
import os
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from app.config import Config
from app.database import Database
from app.sync import ChannelSyncer
from app.logger import logger


def load_env_file():
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())


def print_banner():
    banner = """
╔══════════════════════════════════════════════════════╗
║      🤖  Telegram Channel Cloner  🤖                 ║
║      نظام نسخ قنوات تيليجرام الاحترافي             ║
║      الإصدار 2.0 | بناء احترافي                     ║
╚══════════════════════════════════════════════════════╝
    """
    logger.info(banner)


async def generate_session(config: Config):
    logger.info("🔑 جارٍ إنشاء جلسة جديدة...")
    logger.info("سيُطلب منك رقم الهاتف والرمز التحقق.")
    async with TelegramClient(StringSession(), config.api_id, config.api_hash) as client:
        await client.start()
        session_str = client.session.save()
        logger.info(f"\n✅ تم إنشاء الجلسة بنجاح!\nأضف هذا إلى متغيرات البيئة:\nSESSION_STRING={session_str}\n")
        return session_str


async def main():
    load_env_file()
    print_banner()

    try:
        config = Config.from_env()
    except ValueError as e:
        logger.error(f"❌ خطأ في الإعدادات:\n{e}")
        sys.exit(1)

    logger.info(f"🔧 الإعدادات:")
    logger.info(f"  📡 المصدر: {config.source_channel}")
    logger.info(f"  📥 الهدف: {config.destination_channel}")
    logger.info(f"  📦 حجم الدفعة: {config.batch_size}")
    logger.info(f"  ⏱️  التأخير بين الرسائل: {config.delay_between_messages}ث")

    if not config.session_string:
        session_str = await generate_session(config)
        config.session_string = session_str

    os.makedirs(os.path.dirname(config.db_path), exist_ok=True)
    db = Database(config.db_path)

    client = TelegramClient(
        StringSession(config.session_string),
        config.api_id,
        config.api_hash,
        connection_retries=10,
        retry_delay=5,
        auto_reconnect=True,
        flood_sleep_threshold=60,
    )

    syncer = ChannelSyncer(client, config, db)

    def handle_shutdown(signum, frame):
        logger.info(f"\n🛑 استُلم إشارة الإيقاف ({signum})")
        syncer.stop()
        asyncio.get_event_loop().stop()

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    logger.info("🚀 جارٍ تشغيل البوت...")
    try:
        async with client:
            me = await client.get_me()
            logger.info(f"👤 تم تسجيل الدخول كـ: {me.first_name} (@{me.username})")
            await syncer.run()
    except KeyboardInterrupt:
        logger.info("🛑 تم إيقاف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"❌ خطأ غير متوقع: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("👋 انتهى تشغيل البوت")


if __name__ == "__main__":
    asyncio.run(main())
