import asyncio
from telegram import Bot
from telegram.error import TelegramError, RetryAfter, BadRequest
from app.database import Database
from app.logger import logger


async def copy_archive(
    bot: Bot,
    source_channel: str,
    dest_channel: str,
    db: Database,
    status_chat_id: int,
    start_id: int = 1,
    max_id: int = 50000,
    batch_size: int = 20,
):
    """نسخ الأرشيف الكامل للقناة بالتدريج."""
    copied = 0
    failed = 0
    skipped = 0
    consecutive_missing = 0

    checkpoint_key = f"archive_checkpoint_{source_channel}"
    saved = db.get_setting(checkpoint_key)
    resume_from = int(saved) if saved else start_id

    logger.info(f"📚 بدء نسخ الأرشيف من ID={resume_from} حتى {max_id}")

    try:
        await bot.send_message(
            status_chat_id,
            f"⏳ *جارٍ نسخ الأرشيف...*\n"
            f"من الرسالة رقم `{resume_from}`\n"
            f"قد يستغرق وقتاً حسب حجم القناة.",
            parse_mode="Markdown",
        )
    except Exception:
        pass

    for msg_id in range(resume_from, max_id + 1):
        if db.is_copied(source_channel, msg_id, dest_channel):
            skipped += 1
            consecutive_missing = 0
            continue

        success = await _try_copy(bot, source_channel, dest_channel, msg_id, db)

        if success is True:
            copied += 1
            consecutive_missing = 0
        elif success is False:
            failed += 1
            consecutive_missing = 0
        else:
            # الرسالة غير موجودة
            consecutive_missing += 1

        # حفظ نقطة الاستئناف كل 50 رسالة
        if msg_id % 50 == 0:
            db.set_setting(checkpoint_key, str(msg_id))

        # إرسال تقرير تقدم كل 200 رسالة
        if msg_id % 200 == 0 and (copied + failed) > 0:
            try:
                await bot.send_message(
                    status_chat_id,
                    f"📊 *تقدم النسخ:*\n"
                    f"✅ منسوخ: {copied}\n"
                    f"❌ فاشل: {failed}\n"
                    f"⏭️ متخطى: {skipped}\n"
                    f"📌 آخر ID فُحص: {msg_id}",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

        # إذا تجاوزنا 500 رسالة متتالية غير موجودة، نتوقف
        if consecutive_missing >= 500:
            logger.info(f"🏁 توقف: {consecutive_missing} رسالة متتالية غير موجودة بعد ID={msg_id}")
            break

        # تأخير بسيط لتجنب FloodWait
        await asyncio.sleep(0.05)

    db.set_setting(checkpoint_key, str(msg_id))

    summary = (
        f"✅ *اكتمل نسخ الأرشيف!*\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"✅ منسوخ: *{copied}* رسالة\n"
        f"❌ فاشل: *{failed}* رسالة\n"
        f"⏭️ متخطى (مكرر): *{skipped}* رسالة\n"
        f"📌 آخر ID: *{msg_id}*"
    )

    logger.info(summary.replace("*", "").replace("\n", " | "))

    try:
        await bot.send_message(status_chat_id, summary, parse_mode="Markdown")
    except Exception:
        pass


async def _try_copy(bot: Bot, source: str, dest: str, msg_id: int, db: Database):
    """
    يحاول نسخ رسالة بـ ID معيّن.
    يُعيد: True (نجح) | False (فشل بخطأ) | None (الرسالة غير موجودة)
    """
    for attempt in range(3):
        try:
            sent = await bot.copy_message(
                chat_id=dest,
                from_chat_id=source,
                message_id=msg_id,
            )
            db.mark_copied(source, msg_id, dest, sent.message_id)
            logger.debug(f"✅ {msg_id} → {sent.message_id}")
            return True

        except RetryAfter as e:
            wait = e.retry_after + 1
            logger.warning(f"⚠️ FloodWait {wait}ث عند ID={msg_id}")
            await asyncio.sleep(wait)

        except BadRequest as e:
            err = str(e).lower()
            if any(x in err for x in ["message to copy not found", "message not found", "chat not found"]):
                return None  # غير موجودة — طبيعي
            if "not enough rights" in err or "forbidden" in err:
                logger.error(f"❌ صلاحيات غير كافية: {e}")
                return False
            logger.debug(f"⏭️ ID={msg_id} BadRequest: {e}")
            return None

        except TelegramError as e:
            if attempt == 2:
                logger.warning(f"❌ فشل ID={msg_id}: {e}")
                return False
            await asyncio.sleep(2 * (attempt + 1))

    return False
