"""
نسخ الأرشيف بسرعة عالية — يدعم قنوات مصدر متعددة ومعالجة متوازية.
"""

import asyncio
from typing import Optional
from telegram import Bot
from telegram.error import TelegramError, RetryAfter, BadRequest
from app.database import Database
from app.logger import logger


# عدد الطلبات المتزامنة (معالجة متوازية)
CONCURRENCY = 15
# تأخير FloodWait الافتراضي إذا لم يُحدَّد
DEFAULT_FLOOD_WAIT = 3
# عدد الرسائل الغائبة المتتالية قبل الإيقاف
MAX_MISSING = 300


async def copy_archive(
    bot: Bot,
    source_channel: str,
    dest_channel: str,
    db: Database,
    status_chat_id: int,
    max_id: int = 50_000,
    label: str = "",
):
    """نسخ أرشيف قناة واحدة بمعالجة متوازية عالية السرعة."""
    tag = f"[{label or source_channel[-6:]}]"

    checkpoint_key = f"archive_ckpt_{source_channel}_{dest_channel}"
    resume_from = int(db.get_setting(checkpoint_key) or 1)
    if resume_from > 1:
        logger.info(f"{tag} ↩️ استئناف من ID={resume_from}")

    sem = asyncio.Semaphore(CONCURRENCY)
    counters = {"copied": 0, "skipped": 0, "failed": 0, "missing": 0}
    stop_event = asyncio.Event()
    last_progress_id = [resume_from]

    await _notify(bot, status_chat_id,
                  f"⏳ {tag} *بدأ النسخ السريع*\n"
                  f"من ID `{resume_from}` حتى `{max_id}`\n"
                  f"معالجة متوازية: {CONCURRENCY} طلب في آن واحد")

    async def copy_one(msg_id: int):
        if stop_event.is_set():
            return
        if db.is_msg_copied(source_channel, msg_id, dest_channel):
            counters["skipped"] += 1
            return

        # تحقق من الفلتر
        # (سيتحقق منه copy_message_by_id)

        async with sem:
            result = await _copy_msg(bot, source_channel, dest_channel, msg_id, db)
            if result == "ok":
                counters["copied"] += 1
                counters["missing"] = 0
            elif result == "missing":
                counters["missing"] += 1
            elif result == "filtered":
                counters["skipped"] += 1
            else:
                counters["failed"] += 1

    # تقسيم الرسائل إلى دفعات وتنفيذها بالتوازي
    batch_size = CONCURRENCY * 4
    tasks_done = 0

    for batch_start in range(resume_from, max_id + 1, batch_size):
        if stop_event.is_set():
            break

        batch_end = min(batch_start + batch_size, max_id + 1)
        batch = list(range(batch_start, batch_end))

        await asyncio.gather(*[copy_one(mid) for mid in batch])
        tasks_done += len(batch)

        # حفظ نقطة الاستئناف
        db.set_setting(checkpoint_key, str(batch_end - 1))

        # توقف إذا كل الرسائل الأخيرة غائبة
        if counters["missing"] >= MAX_MISSING:
            logger.info(f"{tag} 🏁 {MAX_MISSING} رسالة غائبة متتالية — اكتمل الأرشيف")
            break

        # تقرير كل 500 رسالة
        if tasks_done % 500 == 0:
            await _notify(bot, status_chat_id,
                          f"📊 {tag} *تقدم النسخ*\n"
                          f"✅ منسوخ: {counters['copied']:,}\n"
                          f"⏭️ متخطى: {counters['skipped']:,}\n"
                          f"❌ فاشل: {counters['failed']:,}\n"
                          f"📌 آخر ID: {batch_end - 1:,}")

    summary = (
        f"✅ {tag} *اكتمل نسخ الأرشيف!*\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"✅ منسوخ: *{counters['copied']:,}*\n"
        f"⏭️ متخطى (مكرر/مفلتر): *{counters['skipped']:,}*\n"
        f"❌ فاشل: *{counters['failed']:,}*"
    )
    await _notify(bot, status_chat_id, summary)
    return counters


async def copy_all_sources(
    bot: Bot,
    db: Database,
    status_chat_id: int,
    max_id: int = 50_000,
):
    """نسخ أرشيف جميع قنوات المصدر بالتوازي."""
    sources = db.get_source_channels()
    dest = db.get_dest_channel()

    if not sources or not dest:
        await _notify(bot, status_chat_id, "❌ لم تُعيَّن القنوات!")
        return

    await _notify(bot, status_chat_id,
                  f"🚀 *بدء نسخ {len(sources)} قناة بالتوازي!*\n"
                  f"📥 الهدف: `{dest}`")

    tasks = [
        copy_archive(bot, src, dest, db, status_chat_id, max_id, label=f"Q{i+1}")
        for i, src in enumerate(sources)
    ]
    await asyncio.gather(*tasks)

    await _notify(bot, status_chat_id,
                  f"🎉 *اكتمل نسخ جميع القنوات ({len(sources)})!*")


async def _copy_msg(
    bot: Bot,
    source: str,
    dest: str,
    msg_id: int,
    db: Database,
) -> str:
    """
    يُعيد: 'ok' | 'missing' | 'filtered' | 'failed'
    """
    for attempt in range(3):
        try:
            sent = await bot.copy_message(
                chat_id=dest,
                from_chat_id=source,
                message_id=msg_id,
            )
            # نحدد النوع من قاعدة البيانات بعد النسخ
            db.mark_copied(source, msg_id, dest, sent.message_id, msg_type="archived")
            logger.debug(f"✅ {msg_id} → {sent.message_id}")
            return "ok"

        except RetryAfter as e:
            wait = max(e.retry_after, 1) + 0.5
            logger.debug(f"⏳ FloodWait {wait:.1f}ث | ID={msg_id}")
            await asyncio.sleep(wait)

        except BadRequest as e:
            err = str(e).lower()
            if any(x in err for x in ["not found", "message to copy", "invalid"]):
                return "missing"
            if any(x in err for x in ["forbidden", "not enough rights", "chat not found"]):
                logger.error(f"❌ صلاحيات: {e}")
                return "failed"
            return "missing"

        except TelegramError as e:
            if attempt == 2:
                logger.debug(f"⚠️ فشل ID={msg_id}: {e}")
                return "failed"
            await asyncio.sleep(1)

    return "failed"


async def _notify(bot: Bot, chat_id: int, text: str):
    try:
        await bot.send_message(chat_id, text, parse_mode="Markdown")
    except Exception:
        pass
