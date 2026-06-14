"""
نسخ الأرشيف بسرعة عالية — فلتر المحتوى + قنوات متعددة + معالجة متوازية.
"""

import asyncio
from typing import Optional, List
from telegram import Bot, Message
from telegram.error import TelegramError, RetryAfter, BadRequest
from app.database import Database
from app.logger import logger


CONCURRENCY  = 15   # طلبات متزامنة بدون فلتر
CONCURRENCY_FILTERED = 5  # طلبات متزامنة مع فلتر (يحتاج forward إضافي)
MAX_MISSING  = 300  # رسائل غائبة متتالية قبل الإيقاف


def _get_msg_type(msg: Message) -> str:
    if msg.photo:       return "photo"
    if msg.video:       return "video"
    if msg.audio:       return "audio"
    if msg.voice:       return "voice"
    if msg.document:    return "document"
    if msg.video_note:  return "video_note"
    if msg.sticker:     return "sticker"
    if msg.animation:   return "animation"
    if msg.text:        return "text"
    return "unknown"


async def copy_archive(
    bot: Bot,
    source_channel: str,
    dest_channel: str,
    db: Database,
    status_chat_id: int,
    max_id: int = 50_000,
    label: str = "",
):
    tag = f"[{label or source_channel[-6:]}]"
    filter_types: List[str] = db.get_filter()
    use_filter = bool(filter_types)

    checkpoint_key = f"archive_ckpt_{source_channel}_{dest_channel}"
    resume_from = int(db.get_setting(checkpoint_key) or 1)
    if resume_from > 1:
        logger.info(f"{tag} ↩️ استئناف من ID={resume_from}")

    concurrency = CONCURRENCY_FILTERED if use_filter else CONCURRENCY
    sem = asyncio.Semaphore(concurrency)
    # mutex لعمليات forward (لتجنب فيضان الرسائل في المحادثة)
    forward_lock = asyncio.Lock() if use_filter else None

    counters = {"copied": 0, "skipped": 0, "filtered": 0, "failed": 0, "missing": 0}

    flt_txt = "الكل" if not filter_types else "+".join(filter_types)
    await _notify(bot, status_chat_id,
                  f"⏳ {tag} *بدأ النسخ*\n"
                  f"الفلتر: `{flt_txt}` | من ID `{resume_from}`\n"
                  f"المعالجة المتوازية: {concurrency}")

    async def copy_one(msg_id: int):
        if db.is_msg_copied(source_channel, msg_id, dest_channel):
            counters["skipped"] += 1
            return

        async with sem:
            result = await _copy_msg(
                bot, source_channel, dest_channel, msg_id, db,
                filter_types, status_chat_id, forward_lock
            )
            if result == "ok":
                counters["copied"]   += 1
                counters["missing"]   = 0
            elif result == "missing":
                counters["missing"] += 1
            elif result == "filtered":
                counters["filtered"] += 1
                counters["missing"]   = 0
            else:
                counters["failed"]  += 1

    batch_size  = concurrency * 4
    tasks_done  = 0

    for batch_start in range(resume_from, max_id + 1, batch_size):
        batch_end = min(batch_start + batch_size, max_id + 1)
        await asyncio.gather(*[copy_one(mid) for mid in range(batch_start, batch_end)])
        tasks_done += batch_end - batch_start

        db.set_setting(checkpoint_key, str(batch_end - 1))

        if counters["missing"] >= MAX_MISSING:
            logger.info(f"{tag} 🏁 {MAX_MISSING} رسالة غائبة — اكتمل الأرشيف")
            break

        if tasks_done % 500 == 0:
            await _notify(bot, status_chat_id,
                          f"📊 {tag} *تقدم*\n"
                          f"✅ {counters['copied']:,} | "
                          f"🚫 {counters['filtered']:,} | "
                          f"⏭️ {counters['skipped']:,} | "
                          f"❌ {counters['failed']:,}\n"
                          f"📌 آخر ID: {batch_end-1:,}")

    await _notify(bot, status_chat_id,
                  f"✅ {tag} *اكتمل!*\n"
                  f"✅ منسوخ: *{counters['copied']:,}*\n"
                  f"🚫 مُفلتَر: *{counters['filtered']:,}*\n"
                  f"⏭️ متخطى: *{counters['skipped']:,}*\n"
                  f"❌ فاشل: *{counters['failed']:,}*")
    return counters


async def copy_all_sources(
    bot: Bot,
    db: Database,
    status_chat_id: int,
    max_id: int = 50_000,
):
    sources = db.get_source_channels()
    dest    = db.get_dest_channel()
    if not sources or not dest:
        await _notify(bot, status_chat_id, "❌ لم تُعيَّن القنوات!")
        return

    flt     = db.get_filter()
    flt_txt = "الكل" if not flt else "+".join(flt)
    await _notify(bot, status_chat_id,
                  f"🚀 *نسخ {len(sources)} قناة بالتوازي!*\n"
                  f"🎚 الفلتر: `{flt_txt}`\n📥 الهدف: `{dest}`")

    await asyncio.gather(*[
        copy_archive(bot, src, dest, db, status_chat_id, max_id, label=f"Q{i+1}")
        for i, src in enumerate(sources)
    ])
    await _notify(bot, status_chat_id,
                  f"🎉 *اكتمل نسخ جميع القنوات ({len(sources)})!*")


# ─────────────────────────────────────────────────────────────────────────────

async def _copy_msg(
    bot: Bot,
    source: str,
    dest: str,
    msg_id: int,
    db: Database,
    filter_types: List[str],
    status_chat_id: int,
    forward_lock: Optional[asyncio.Lock],
) -> str:
    """
    إذا كان الفلتر مفعَّلاً:
      1- forward الرسالة للأدمن (لمعرفة نوعها)
      2- احذفها فوراً
      3- انسخها للهدف إذا تطابق النوع مع الفلتر
    إذا لم يكن هناك فلتر: copy_message مباشرة (أسرع).
    """
    for attempt in range(3):
        try:
            if filter_types:
                # ── نحدد النوع أولاً عبر forward مؤقت ──────────────
                msg_type = await _inspect_type(
                    bot, source, msg_id, status_chat_id, forward_lock
                )
                if msg_type == "missing":
                    return "missing"
                if msg_type and msg_type not in filter_types:
                    # سجّل كـ "filtered" لتجنب إعادة الفحص
                    db.mark_copied(source, msg_id, dest, None, msg_type=msg_type)
                    return "filtered"

            # ── النسخ الفعلي ──────────────────────────────────────
            sent = await bot.copy_message(
                chat_id=dest,
                from_chat_id=source,
                message_id=msg_id,
            )
            db.mark_copied(source, msg_id, dest, sent.message_id,
                           msg_type=filter_types[0] if filter_types else "archived")
            return "ok"

        except RetryAfter as e:
            await asyncio.sleep(max(e.retry_after, 1) + 0.5)

        except BadRequest as e:
            err = str(e).lower()
            if any(x in err for x in ["not found", "message to copy", "invalid", "message_id_invalid"]):
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


async def _inspect_type(
    bot: Bot,
    source: str,
    msg_id: int,
    staging_chat: int,
    lock: Optional[asyncio.Lock],
) -> Optional[str]:
    """
    يُحوِّل الرسالة مؤقتاً إلى محادثة الأدمن لمعرفة نوعها ثم يحذفها.
    """
    async def do_inspect():
        try:
            fwd = await bot.forward_message(
                chat_id=staging_chat,
                from_chat_id=source,
                message_id=msg_id,
            )
            msg_type = _get_msg_type(fwd)
            try:
                await bot.delete_message(chat_id=staging_chat, message_id=fwd.message_id)
            except Exception:
                pass
            return msg_type
        except BadRequest as e:
            err = str(e).lower()
            if any(x in err for x in ["not found", "message_id_invalid", "message to forward"]):
                return "missing"
            return None
        except TelegramError:
            return None

    if lock:
        async with lock:
            return await do_inspect()
    return await do_inspect()


async def _notify(bot: Bot, chat_id: int, text: str):
    try:
        await bot.send_message(chat_id, text, parse_mode="Markdown")
    except Exception:
        pass
