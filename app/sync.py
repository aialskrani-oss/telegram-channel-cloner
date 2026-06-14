import asyncio
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.errors import FloodWaitError
from app.logger import logger
from app.database import Database
from app.config import Config
from app.copier import MessageCopier


class ChannelSyncer:
    def __init__(self, client: TelegramClient, config: Config, db: Database):
        self.client = client
        self.config = config
        self.db = db
        self.copier = MessageCopier(client, config, db)
        self.source_entity = None
        self.dest_entity = None
        self._running = False

    async def _resolve_channels(self):
        logger.info(f"🔍 جارٍ تحليل القنوات...")
        self.source_entity = await self.client.get_entity(self.config.source_channel)
        self.dest_entity = await self.client.get_entity(self.config.destination_channel)
        logger.info(f"📡 القناة المصدر: {getattr(self.source_entity, 'title', self.config.source_channel)}")
        logger.info(f"📥 القناة الهدف: {getattr(self.dest_entity, 'title', self.config.destination_channel)}")

    async def _get_total_messages(self) -> int:
        try:
            full = await self.client(GetFullChannelRequest(self.source_entity))
            return full.full_chat.read_inbox_max_id or 0
        except Exception:
            return 0

    async def archive_history(self):
        logger.info("📚 بدء نسخ الأرشيف الكامل...")
        last_id = self.db.get_checkpoint(
            str(self.source_entity.id), str(self.dest_entity.id)
        )

        if last_id:
            logger.info(f"↩️  استئناف من الرسالة {last_id}")

        copied = 0
        failed = 0
        batch_count = 0

        async for msg in self.client.iter_messages(
            self.source_entity,
            reverse=True,
            min_id=last_id,
            limit=None,
        ):
            if not self._running:
                break

            success = await self.copier.copy_message(msg, self.source_entity, self.dest_entity)
            if success:
                copied += 1
            else:
                failed += 1

            batch_count += 1

            if batch_count % self.config.batch_size == 0:
                self.db.update_checkpoint(
                    str(self.source_entity.id), str(self.dest_entity.id),
                    msg.id, copied, failed
                )
                logger.info(
                    f"📊 تقدم: {batch_count} رسالة | ✅ {copied} | ❌ {failed} | "
                    f"آخر ID: {msg.id}"
                )
                copied = 0
                failed = 0
                await asyncio.sleep(self.config.delay_between_batches)
            else:
                await asyncio.sleep(self.config.delay_between_messages)

        if copied > 0 or failed > 0:
            self.db.update_checkpoint(
                str(self.source_entity.id), str(self.dest_entity.id),
                batch_count, copied, failed
            )

        logger.info("✅ اكتمل نسخ الأرشيف بنجاح!")
        await self.copier.retry_failed(self.source_entity, self.dest_entity)
        self._print_stats()

    async def start_live_sync(self):
        logger.info("🔴 بدء المزامنة المباشرة للرسائل الجديدة...")

        @self.client.on(events.NewMessage(chats=self.source_entity))
        async def handler(event):
            msg = event.message
            logger.info(f"📨 رسالة جديدة {msg.id} - جارٍ النسخ...")
            for attempt in range(3):
                try:
                    success = await self.copier.copy_message(msg, self.source_entity, self.dest_entity)
                    if success:
                        logger.info(f"✅ تم نسخ الرسالة الجديدة {msg.id}")
                    break
                except FloodWaitError as e:
                    logger.warning(f"⚠️  FloodWait {e.seconds}ث، الانتظار...")
                    await asyncio.sleep(e.seconds + 5)
                except Exception as e:
                    logger.error(f"❌ خطأ في نسخ الرسالة {msg.id}: {e}")
                    if attempt == 2:
                        break
                    await asyncio.sleep(5)

        logger.info("👂 يستمع للرسائل الجديدة...")
        await self.client.run_until_disconnected()

    async def run(self):
        self._running = True
        await self._resolve_channels()
        await self.archive_history()
        await self.start_live_sync()

    def stop(self):
        self._running = False
        logger.info("🛑 جارٍ إيقاف المزامنة...")

    def _print_stats(self):
        stats = self.db.get_stats(
            str(self.source_entity.id), str(self.dest_entity.id)
        )
        logger.info("━" * 50)
        logger.info("📈 إحصائيات النسخ:")
        logger.info(f"  ✅ ناجح: {stats['success']}")
        logger.info(f"  ❌ فاشل: {stats['failed']}")
        logger.info(f"  ⏸️  معلق: {stats['pending']}")
        logger.info(f"  📌 آخر ID: {stats['last_processed_id']}")
        logger.info(f"  🕐 آخر مزامنة: {stats['last_synced_at']}")
        logger.info("━" * 50)
