import asyncio
from typing import Optional
from telethon import TelegramClient
from telethon.tl.types import (
    Message, MessageMediaPhoto, MessageMediaDocument,
    MessageMediaWebPage, InputChannel
)
from telethon.errors import (
    FloodWaitError, ChatWriteForbiddenError,
    ChannelPrivateError, MediaEmptyError, FileReferenceExpiredError
)
from app.logger import logger
from app.database import Database
from app.config import Config


def _get_message_type(msg: Message) -> str:
    if msg.photo:
        return "photo"
    if msg.video:
        return "video"
    if msg.audio:
        return "audio"
    if msg.voice:
        return "voice"
    if msg.document:
        return "document"
    if msg.sticker:
        return "sticker"
    if msg.gif:
        return "gif"
    if msg.text:
        return "text"
    return "unknown"


class MessageCopier:
    def __init__(self, client: TelegramClient, config: Config, db: Database):
        self.client = client
        self.config = config
        self.db = db

    async def copy_message(self, msg: Message, source_entity, dest_entity) -> bool:
        if self.db.is_message_copied(msg.id, str(source_entity.id), str(dest_entity.id)):
            logger.debug(f"⏭️  الرسالة {msg.id} منسوخة مسبقاً، تخطي...")
            return True

        msg_type = _get_message_type(msg)
        source_id = str(source_entity.id)
        dest_id = str(dest_entity.id)

        for attempt in range(1, self.config.max_retries + 1):
            try:
                sent = await self._do_copy(msg, dest_entity)
                if sent:
                    self.db.save_message(msg.id, sent.id, source_id, dest_id, msg_type, "success")
                    logger.debug(f"✅ نُسخت الرسالة {msg.id} ({msg_type}) → {sent.id}")
                    return True
                else:
                    self.db.save_message(msg.id, None, source_id, dest_id, msg_type, "skipped")
                    return True

            except FloodWaitError as e:
                wait = e.seconds + 5
                logger.warning(f"⚠️  FloodWait {wait}ث للرسالة {msg.id}. الانتظار...")
                await asyncio.sleep(wait)

            except (ChatWriteForbiddenError, ChannelPrivateError) as e:
                logger.error(f"❌ خطأ في الصلاحيات: {e}")
                self.db.save_message(msg.id, None, source_id, dest_id, msg_type, "failed", str(e))
                return False

            except (MediaEmptyError, FileReferenceExpiredError) as e:
                logger.warning(f"⚠️  خطأ في الوسائط للرسالة {msg.id}: {e}. محاولة إرسال النص فقط...")
                try:
                    if msg.text:
                        sent = await self.client.send_message(dest_entity, msg.text)
                        self.db.save_message(msg.id, sent.id, source_id, dest_id, "text_fallback", "success")
                        return True
                except Exception as inner:
                    logger.error(f"❌ فشل إرسال النص البديل: {inner}")
                self.db.save_message(msg.id, None, source_id, dest_id, msg_type, "failed", str(e))
                return False

            except Exception as e:
                if attempt < self.config.max_retries:
                    logger.warning(f"⚠️  محاولة {attempt}/{self.config.max_retries} للرسالة {msg.id} فشلت: {e}")
                    await asyncio.sleep(self.config.retry_delay * attempt)
                else:
                    logger.error(f"❌ فشلت الرسالة {msg.id} بعد {self.config.max_retries} محاولات: {e}")
                    self.db.save_message(msg.id, None, source_id, dest_id, msg_type, "failed", str(e))
                    return False

        return False

    async def _do_copy(self, msg: Message, dest_entity) -> Optional[Message]:
        if not msg.media and not msg.text:
            return None

        if msg.media and not isinstance(msg.media, MessageMediaWebPage):
            return await self.client.send_file(
                dest_entity,
                file=msg.media,
                caption=msg.text or "",
                parse_mode="html",
                voice_note=bool(msg.voice),
                video_note=bool(msg.video_note),
                force_document=isinstance(msg.media, MessageMediaDocument) and not msg.gif and not msg.video,
            )

        if msg.text:
            return await self.client.send_message(
                dest_entity,
                msg.text,
                parse_mode="html",
                link_preview=isinstance(msg.media, MessageMediaWebPage),
            )

        return None

    async def retry_failed(self, source_entity, dest_entity):
        failed = self.db.get_failed_messages(
            str(source_entity.id), str(dest_entity.id), self.config.max_retries
        )
        if not failed:
            return

        logger.info(f"🔄 إعادة محاولة {len(failed)} رسالة فاشلة...")
        for row in failed:
            try:
                msg = await self.client.get_messages(source_entity, ids=row["source_message_id"])
                if msg:
                    await self.copy_message(msg, source_entity, dest_entity)
                    await asyncio.sleep(self.config.delay_between_messages)
            except Exception as e:
                logger.error(f"❌ فشل إعادة المحاولة للرسالة {row['source_message_id']}: {e}")
