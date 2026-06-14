"""
معالج مجموعات الوسائط (Albums / Media Groups).
يجمع رسائل الألبوم الواحد ويُرسلها دفعة واحدة محافظةً على التجميع.
"""

import asyncio
from typing import Dict, List, Optional, Tuple
from telegram import Bot, Message, InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio
from telegram.error import TelegramError, RetryAfter, BadRequest
from app.database import Database
from app.logger import logger


COLLECT_DELAY = 3.0   # ثواني انتظار (كافية لاستقبال كل رسائل الألبوم)

# مخزن مؤقت: gid → (قائمة الرسائل، مؤقت asyncio)
_buffers: Dict[str, List[Message]] = {}
_timers:  Dict[str, asyncio.Task]  = {}
_locks:   Dict[str, asyncio.Lock]  = {}   # mutex لكل مجموعة


def _get_or_create_lock(gid: str) -> asyncio.Lock:
    if gid not in _locks:
        _locks[gid] = asyncio.Lock()
    return _locks[gid]


async def handle_media_group_message(
    bot: Bot,
    msg: Message,
    dest_chat: str,
    db: Database,
) -> None:
    """استقبال رسالة من ألبوم، تخزينها ومزامنة الإرسال بعد اكتمال المجموعة."""
    gid = msg.media_group_id
    if not gid:
        return

    # ── فلتر المحتوى ──────────────────────────────────────
    msg_type = _get_type(msg)
    if not db.is_type_allowed(msg_type):
        logger.debug(f"🚫 ألبوم مُفلتَر ({msg_type}) | {msg.message_id}")
        return

    lock = _get_or_create_lock(gid)
    async with lock:
        if gid not in _buffers:
            _buffers[gid] = []
        _buffers[gid].append(msg)

        # إلغاء المؤقت القديم وإنشاء مؤقت جديد
        old = _timers.get(gid)
        if old and not old.done():
            old.cancel()
            try:
                await asyncio.shield(asyncio.sleep(0))  # نتيح للحلقة تنفيذ الإلغاء
            except asyncio.CancelledError:
                pass

        _timers[gid] = asyncio.create_task(
            _flush_after_delay(bot, gid, dest_chat, db)
        )

    logger.debug(f"📦 ألبوم {gid}: {len(_buffers.get(gid, []))} رسالة مُخزَّنة")


async def _flush_after_delay(
    bot: Bot,
    gid: str,
    dest_chat: str,
    db: Database,
) -> None:
    """انتظر COLLECT_DELAY ثم أرسل المجموعة."""
    try:
        await asyncio.sleep(COLLECT_DELAY)
    except asyncio.CancelledError:
        return   # مؤقت جديد سيأخذ مكانه

    lock = _get_or_create_lock(gid)
    async with lock:
        messages = _buffers.pop(gid, [])
        _timers.pop(gid, None)
        _locks.pop(gid, None)

    if not messages:
        return

    messages.sort(key=lambda m: m.message_id)
    source = str(messages[0].chat_id)

    # فحص التكرار
    all_copied = all(db.is_msg_copied(source, m.message_id, dest_chat) for m in messages)
    if all_copied:
        logger.debug(f"⏭️ مجموعة {gid} منسوخة مسبقاً")
        return

    logger.info(f"📦 إرسال مجموعة {gid}: {len(messages)} وسائط")

    media_list, indexed = _build_input_media(messages)

    if not media_list:
        logger.warning(f"⚠️ مجموعة {gid}: لا وسائط صالحة للإرسال")
        return

    # ── محاولة الإرسال الجماعي ────────────────────────────
    for attempt in range(1, 4):
        try:
            sent_msgs = await bot.send_media_group(chat_id=dest_chat, media=media_list)
            for i, src_msg in enumerate(indexed):
                dest_id = sent_msgs[i].message_id if i < len(sent_msgs) else None
                fid, mtype = _get_file_info(src_msg)
                db.mark_copied(source, src_msg.message_id, dest_chat, dest_id,
                               media_file_id=fid, msg_type=mtype)
            logger.info(f"✅ مجموعة {gid}: أُرسلت {len(sent_msgs)} وسائط")
            return

        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)

        except BadRequest as e:
            logger.error(f"❌ BadRequest مجموعة {gid}: {e}")
            await _fallback_single(bot, messages, dest_chat, db)
            return

        except TelegramError as e:
            if attempt == 3:
                logger.error(f"❌ فشل مجموعة {gid}: {e}")
                await _fallback_single(bot, messages, dest_chat, db)
            else:
                await asyncio.sleep(attempt * 2)


def _build_input_media(messages: List[Message]) -> Tuple[list, List[Message]]:
    """
    يبني قائمة InputMedia ويُعيد أيضاً قائمة الرسائل المدرجة بنفس الترتيب.
    الرسائل التي لا تدعمها send_media_group تُتجاهل.
    """
    media_list = []
    indexed    = []   # الرسائل المقابلة لكل عنصر في media_list
    for msg in messages:
        caption    = msg.caption_html if msg.caption else None
        parse_mode = "HTML" if caption else None

        if msg.photo:
            media_list.append(InputMediaPhoto(
                media=msg.photo[-1].file_id, caption=caption, parse_mode=parse_mode))
            indexed.append(msg)
        elif msg.video:
            media_list.append(InputMediaVideo(
                media=msg.video.file_id, caption=caption, parse_mode=parse_mode))
            indexed.append(msg)
        elif msg.document:
            media_list.append(InputMediaDocument(
                media=msg.document.file_id, caption=caption, parse_mode=parse_mode))
            indexed.append(msg)
        elif msg.audio:
            media_list.append(InputMediaAudio(
                media=msg.audio.file_id, caption=caption, parse_mode=parse_mode))
            indexed.append(msg)
        # أنواع أخرى (sticker, voice, video_note) لا تدعمها media_group

    return media_list, indexed


async def _fallback_single(
    bot: Bot,
    messages: List[Message],
    dest_chat: str,
    db: Database,
) -> None:
    """إرسال واحدة واحدة إذا فشل send_media_group."""
    from app.copier import copy_message_to_channel
    logger.info("🔄 إرسال رسائل المجموعة واحدة تلو الأخرى (احتياطي)...")
    for msg in messages:
        await copy_message_to_channel(bot, msg, dest_chat, db)
        await asyncio.sleep(0.5)


def _get_type(msg: Message) -> str:
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


def _get_file_info(msg: Message) -> Tuple[Optional[str], str]:
    if msg.photo:    return msg.photo[-1].file_id, "photo"
    if msg.video:    return msg.video.file_id,     "video"
    if msg.document: return msg.document.file_id,  "document"
    if msg.audio:    return msg.audio.file_id,     "audio"
    return None, "unknown"
