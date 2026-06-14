import asyncio
from telegram import Bot, Message
from telegram.error import TelegramError, RetryAfter, BadRequest
from app.database import Database
from app.logger import logger


async def copy_message_to_channel(
    bot: Bot,
    message: Message,
    dest_chat_id: str,
    db: Database,
) -> bool:
    source_chat = str(message.chat_id)
    msg_id = message.message_id

    if db.is_copied(source_chat, msg_id, dest_chat_id):
        logger.debug(f"⏭️ الرسالة {msg_id} منسوخة مسبقاً")
        return True

    for attempt in range(1, 6):
        try:
            sent = await _do_copy(bot, message, dest_chat_id)
            dest_id = sent.message_id if sent else None
            db.mark_copied(source_chat, msg_id, dest_chat_id, dest_id)
            logger.info(f"✅ نُسخت الرسالة {msg_id} ← {dest_id}")
            return True

        except RetryAfter as e:
            logger.warning(f"⚠️ FloodWait {e.retry_after}ث ...")
            await asyncio.sleep(e.retry_after + 1)

        except BadRequest as e:
            logger.error(f"❌ BadRequest للرسالة {msg_id}: {e}")
            db.mark_copied(source_chat, msg_id, dest_chat_id, None)
            return False

        except TelegramError as e:
            if attempt < 5:
                wait = attempt * 3
                logger.warning(f"⚠️ محاولة {attempt}/5 للرسالة {msg_id}: {e} — انتظار {wait}ث")
                await asyncio.sleep(wait)
            else:
                logger.error(f"❌ فشل نسخ الرسالة {msg_id} بعد 5 محاولات: {e}")
                return False

    return False


async def _do_copy(bot: Bot, msg: Message, dest: str) -> Message:
    caption = msg.caption_html if msg.caption else None
    parse_mode = "HTML"

    if msg.photo:
        return await bot.send_photo(dest, msg.photo[-1].file_id, caption=caption, parse_mode=parse_mode)

    if msg.video:
        return await bot.send_video(dest, msg.video.file_id, caption=caption, parse_mode=parse_mode)

    if msg.audio:
        return await bot.send_audio(dest, msg.audio.file_id, caption=caption, parse_mode=parse_mode)

    if msg.voice:
        return await bot.send_voice(dest, msg.voice.file_id, caption=caption, parse_mode=parse_mode)

    if msg.document:
        return await bot.send_document(dest, msg.document.file_id, caption=caption, parse_mode=parse_mode)

    if msg.video_note:
        return await bot.send_video_note(dest, msg.video_note.file_id)

    if msg.sticker:
        return await bot.send_sticker(dest, msg.sticker.file_id)

    if msg.animation:
        return await bot.send_animation(dest, msg.animation.file_id, caption=caption, parse_mode=parse_mode)

    if msg.text:
        return await bot.send_message(dest, msg.text_html, parse_mode=parse_mode)

    if msg.poll and not msg.poll.is_anonymous is False:
        return await bot.forward_message(dest, msg.chat_id, msg.message_id)

    return await bot.forward_message(dest, msg.chat_id, msg.message_id)
