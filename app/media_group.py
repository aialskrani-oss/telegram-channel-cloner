"""
معالج مجموعات الوسائط (Albums / Media Groups)
يجمع رسائل الألبوم ثم يُرسلها دفعة واحدة للحفاظ على التجميع.
"""

import asyncio
from typing import Dict, List, Optional
from telegram import Bot, Message, InputMediaPhoto, InputMediaVideo, InputMediaDocument, InputMediaAudio
from telegram.error import TelegramError, RetryAfter, BadRequest
from app.database import Database
from app.logger import logger


# مخزن مؤقت: media_group_id → قائمة الرسائل
_buffers: Dict[str, List[Message]] = {}
_timers:  Dict[str, asyncio.Task]  = {}

COLLECT_DELAY = 1.5  # ثواني انتظار لجمع رسائل المجموعة


async def handle_media_group_message(
    bot: Bot,
    msg: Message,
    dest_chat: str,
    db: Database,
) -> None:
    """استقبال رسالة من ألبوم وتأجيل الإرسال حتى اكتمال المجموعة."""
    gid = msg.media_group_id
    if not gid:
        return

    # إضافة الرسالة للمخزن المؤقت
    if gid not in _buffers:
        _buffers[gid] = []
    _buffers[gid].append(msg)

    # إلغاء المؤقت السابق وإعادة الجدولة
    if gid in _timers and not _timers[gid].done():
        _timers[gid].cancel()

    _timers[gid] = asyncio.create_task(
        _flush_group(bot, gid, dest_chat, db)
    )


async def _flush_group(
    bot: Bot,
    gid: str,
    dest_chat: str,
    db: Database,
) -> None:
    """انتظر قليلاً ثم أرسل المجموعة كاملة."""
    await asyncio.sleep(COLLECT_DELAY)

    messages = _buffers.pop(gid, [])
    _timers.pop(gid, None)

    if not messages:
        return

    # ترتيب الرسائل بـ message_id
    messages.sort(key=lambda m: m.message_id)

    source = str(messages[0].chat_id)

    # تحقق هل المجموعة كلها منسوخة مسبقاً
    all_copied = all(
        db.is_msg_copied(source, m.message_id, dest_chat)
        for m in messages
    )
    if all_copied:
        logger.debug(f"⏭️ مجموعة {gid} منسوخة مسبقاً ({len(messages)} رسالة)")
        return

    logger.info(f"📦 مجموعة وسائط {gid}: {len(messages)} رسالة → إرسال دفعة واحدة")

    media_list = _build_input_media(messages)

    if not media_list:
        logger.warning(f"⚠️ لا توجد وسائط صالحة في المجموعة {gid}")
        return

    for attempt in range(1, 4):
        try:
            sent_msgs = await bot.send_media_group(
                chat_id=dest_chat,
                media=media_list,
            )

            # تسجيل كل رسالة في قاعدة البيانات
            for i, src_msg in enumerate(messages):
                dest_id = sent_msgs[i].message_id if i < len(sent_msgs) else None
                file_id, msg_type = _get_file_info(src_msg)
                db.mark_copied(
                    source, src_msg.message_id, dest_chat, dest_id,
                    media_file_id=file_id,
                    msg_type=msg_type,
                )

            logger.info(f"✅ مجموعة {gid}: أُرسلت {len(sent_msgs)} وسائط بنجاح")
            return

        except RetryAfter as e:
            wait = e.retry_after + 1
            logger.warning(f"⚠️ FloodWait {wait}ث للمجموعة {gid}")
            await asyncio.sleep(wait)

        except BadRequest as e:
            logger.error(f"❌ BadRequest للمجموعة {gid}: {e}")
            # احتياط: أرسل واحدة واحدة إذا فشل الإرسال الجماعي
            await _fallback_single(bot, messages, dest_chat, db)
            return

        except TelegramError as e:
            if attempt == 3:
                logger.error(f"❌ فشل إرسال المجموعة {gid}: {e}")
                await _fallback_single(bot, messages, dest_chat, db)
            else:
                await asyncio.sleep(attempt * 2)


def _build_input_media(messages: List[Message]) -> list:
    """تحويل قائمة رسائل إلى InputMedia للإرسال الجماعي."""
    media_list = []
    for i, msg in enumerate(messages):
        # الوصف فقط على أول رسالة أو آخر رسالة في المجموعة
        caption     = msg.caption_html if msg.caption else None
        parse_mode  = "HTML" if caption else None

        if msg.photo:
            media_list.append(InputMediaPhoto(
                media=msg.photo[-1].file_id,
                caption=caption,
                parse_mode=parse_mode,
            ))
        elif msg.video:
            media_list.append(InputMediaVideo(
                media=msg.video.file_id,
                caption=caption,
                parse_mode=parse_mode,
            ))
        elif msg.document:
            media_list.append(InputMediaDocument(
                media=msg.document.file_id,
                caption=caption,
                parse_mode=parse_mode,
            ))
        elif msg.audio:
            media_list.append(InputMediaAudio(
                media=msg.audio.file_id,
                caption=caption,
                parse_mode=parse_mode,
            ))
        # الأنواع غير المدعومة في send_media_group تُتجاهل

    return media_list


async def _fallback_single(
    bot: Bot,
    messages: List[Message],
    dest_chat: str,
    db: Database,
) -> None:
    """خطة احتياطية: أرسل كل رسالة لوحدها إذا فشل الإرسال الجماعي."""
    from app.copier import copy_message_to_channel
    logger.info(f"🔄 إرسال المجموعة رسالة رسالة (وضع احتياطي)...")
    for msg in messages:
        await copy_message_to_channel(bot, msg, dest_chat, db)
        await asyncio.sleep(0.3)


def _get_file_info(msg: Message):
    """استخراج file_id ونوع الوسيط."""
    if msg.photo:    return msg.photo[-1].file_id, "photo"
    if msg.video:    return msg.video.file_id,     "video"
    if msg.document: return msg.document.file_id,  "document"
    if msg.audio:    return msg.audio.file_id,     "audio"
    return None, "unknown"
