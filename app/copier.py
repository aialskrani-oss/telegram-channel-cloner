import asyncio
import hashlib
from typing import Optional, Tuple
from telegram import Bot, Message
from telegram.error import TelegramError, RetryAfter, BadRequest
from app.database import Database
from app.logger import logger


def _extract_media(msg: Message) -> Tuple[Optional[str], str]:
    if msg.photo:      return msg.photo[-1].file_id, "photo"
    if msg.video:      return msg.video.file_id,     "video"
    if msg.audio:      return msg.audio.file_id,     "audio"
    if msg.voice:      return msg.voice.file_id,     "voice"
    if msg.document:   return msg.document.file_id,  "document"
    if msg.video_note: return msg.video_note.file_id,"video_note"
    if msg.sticker:    return msg.sticker.file_id,   "sticker"
    if msg.animation:  return msg.animation.file_id, "animation"
    if msg.text:       return None,                  "text"
    return None, "unknown"


def _text_hash(text: Optional[str]) -> Optional[str]:
    if not text or len(text.strip()) < 10:
        return None
    return hashlib.sha256(text.strip().encode()).hexdigest()


async def copy_message_to_channel(
    bot: Bot,
    message: Message,
    dest_chat_id: str,
    db: Database,
) -> bool:
    source   = str(message.chat_id)
    msg_id   = message.message_id
    file_id, msg_type = _extract_media(message)

    # ── فلتر المحتوى ───────────────────────────────────────
    if not db.is_type_allowed(msg_type):
        logger.debug(f"🚫 مُفلتَر ({msg_type}) | الرسالة {msg_id}")
        return True

    # ── منع التكرار (3 طبقات) ──────────────────────────────
    if db.is_msg_copied(source, msg_id, dest_chat_id):
        logger.debug(f"⏭️ مكرر (msg_id) | {msg_id}")
        return True
    if file_id and db.is_file_copied(file_id, dest_chat_id):
        db.mark_copied(source, msg_id, dest_chat_id, None, media_file_id=file_id, msg_type=msg_type)
        logger.debug(f"⏭️ مكرر (file_id) | {msg_id}")
        return True
    if message.text:
        h = _text_hash(message.text)
        if h and db.is_text_copied(h, dest_chat_id):
            db.mark_copied(source, msg_id, dest_chat_id, None, text_hash=h, msg_type="text")
            logger.debug(f"⏭️ مكرر (نص) | {msg_id}")
            return True

    text_hash = _text_hash(message.text) if message.text and not file_id else None

    for attempt in range(1, 6):
        try:
            sent = await _do_copy(bot, message, dest_chat_id)
            dest_id = sent.message_id if sent else None
            db.mark_copied(source, msg_id, dest_chat_id, dest_id,
                           media_file_id=file_id, text_hash=text_hash, msg_type=msg_type)
            logger.info(f"✅ {msg_type} {msg_id} → {dest_id}")
            return True

        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except BadRequest as e:
            logger.error(f"❌ BadRequest {msg_id}: {e}")
            db.mark_copied(source, msg_id, dest_chat_id, None, msg_type=msg_type)
            return False
        except TelegramError as e:
            if attempt < 5:
                await asyncio.sleep(attempt * 2)
            else:
                logger.error(f"❌ فشل {msg_id}: {e}")
                return False
    return False


async def _do_copy(bot: Bot, msg: Message, dest: str) -> Message:
    cap  = msg.caption_html if msg.caption else None
    html = "HTML"
    if msg.photo:      return await bot.send_photo(dest, msg.photo[-1].file_id, caption=cap, parse_mode=html)
    if msg.video:      return await bot.send_video(dest, msg.video.file_id, caption=cap, parse_mode=html)
    if msg.audio:      return await bot.send_audio(dest, msg.audio.file_id, caption=cap, parse_mode=html)
    if msg.voice:      return await bot.send_voice(dest, msg.voice.file_id, caption=cap, parse_mode=html)
    if msg.document:   return await bot.send_document(dest, msg.document.file_id, caption=cap, parse_mode=html)
    if msg.video_note: return await bot.send_video_note(dest, msg.video_note.file_id)
    if msg.sticker:    return await bot.send_sticker(dest, msg.sticker.file_id)
    if msg.animation:  return await bot.send_animation(dest, msg.animation.file_id, caption=cap, parse_mode=html)
    if msg.text:       return await bot.send_message(dest, msg.text_html, parse_mode=html)
    return await bot.forward_message(dest, msg.chat_id, msg.message_id)
