import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from app.database import Database
from app.config import Config
from app.copier import copy_message_to_channel
from app.media_group import handle_media_group_message
from app.logger import logger

TYPE_ICONS = {
    "photo": "🖼", "video": "🎥", "audio": "🎵", "voice": "🎤",
    "document": "📄", "sticker": "🎭", "animation": "🎞",
    "video_note": "📹", "text": "💬", "unknown": "❓",
}
ALL_TYPES = list(TYPE_ICONS.keys())[:-1]  # بدون unknown

def is_admin(user_id: int, config: Config) -> bool:
    return not config.admin_ids or user_id in config.admin_ids


# ═══════════════════════════════════════════════════
# /start
# ═══════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    sources = db.get_source_channels()
    dst     = db.get_dest_channel() or "❌ غير محددة"
    flt     = db.get_filter()
    stats   = db.get_stats()
    flt_txt = "الكل" if not flt else " + ".join(TYPE_ICONS.get(t,"") + t for t in flt)

    src_lines = "\n".join(f"  `{s}`" for s in sources) if sources else "  ❌ لا توجد"

    await update.message.reply_text(
        "🤖 *بوت نسخ القنوات — v4.0*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"📡 *المصادر ({len(sources)}):\n*{src_lines}\n"
        f"📥 *الهدف:* `{dst}`\n"
        f"🎚 *الفلتر:* {flt_txt}\n"
        f"📊 *الإجمالي:* {stats['total']:,} | اليوم: {stats['today']:,}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "*أوامر المصدر:*\n"
        "/addsource — إضافة قناة مصدر\n"
        "/removesource — حذف قناة مصدر\n"
        "/listsources — عرض قنوات المصدر\n\n"
        "*أوامر الهدف:*\n"
        "/setdest — تعيين الهدف\n\n"
        "*الفلتر:*\n"
        "/setfilter — تحديد نوع المحتوى\n"
        "/clearfilter — إلغاء الفلتر (كل شيء)\n\n"
        "*الأرشيف:*\n"
        "/copyarchive — نسخ كل الرسائل القديمة\n"
        "/stoparchive — إيقاف النسخ\n\n"
        "/status /stats /help",
        parse_mode="Markdown",
    )


# ═══════════════════════════════════════════════════
# /chatid
# ═══════════════════════════════════════════════════
async def cmd_chatid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    await update.effective_message.reply_text(
        f"🆔 *معرّف هذه القناة:*\n`{chat.id}`\n\n"
        f"📛 {getattr(chat,'title','-')}\n"
        f"استخدمه مع:\n`/addsource {chat.id}`\n`/setdest {chat.id}`",
        parse_mode="Markdown",
    )


# ═══════════════════════════════════════════════════
# /addsource <id>   أو  /setsourceme (داخل القناة)
# ═══════════════════════════════════════════════════
async def cmd_add_source(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    if not ctx.args:
        await update.message.reply_text(
            "📌 `/addsource -1001234567890`\n"
            "أو أضفني في القناة وأرسل `/setsourceme`",
            parse_mode="Markdown")
        return
    ch = ctx.args[0].strip()
    added = db.add_source_channel(ch)
    sources = db.get_source_channels()
    if added:
        await update.message.reply_text(
            f"✅ تمت إضافة المصدر: `{ch}`\n"
            f"إجمالي المصادر: *{len(sources)}*", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"ℹ️ المصدر `{ch}` موجود مسبقاً.", parse_mode="Markdown")

async def cmd_set_source_me(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    chat_id = str(update.effective_chat.id)
    title   = getattr(update.effective_chat, "title", chat_id)
    added   = db.add_source_channel(chat_id)
    msg = f"✅ *تمت إضافة هذه القناة كمصدر!*\n📛 {title}\n🆔 `{chat_id}`" \
          if added else f"ℹ️ هذه القناة موجودة مسبقاً كمصدر.\n🆔 `{chat_id}`"
    await update.effective_message.reply_text(msg, parse_mode="Markdown")


# ═══════════════════════════════════════════════════
# /removesource <id>
# ═══════════════════════════════════════════════════
async def cmd_remove_source(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    if not ctx.args:
        sources = db.get_source_channels()
        lines   = "\n".join(f"`{s}`" for s in sources) or "لا توجد مصادر"
        await update.message.reply_text(
            f"📌 `/removesource <id>`\n\n*المصادر الحالية:*\n{lines}",
            parse_mode="Markdown")
        return
    ch = ctx.args[0].strip()
    removed = db.remove_source_channel(ch)
    if removed:
        await update.message.reply_text(f"🗑 تمت إزالة المصدر: `{ch}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ المصدر `{ch}` غير موجود.", parse_mode="Markdown")


# ═══════════════════════════════════════════════════
# /listsources
# ═══════════════════════════════════════════════════
async def cmd_list_sources(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    sources = db.get_source_channels()
    if not sources:
        await update.message.reply_text("❌ لا توجد قنوات مصدر بعد.\nاستخدم `/addsource`", parse_mode="Markdown")
        return
    lines = "\n".join(f"{i+1}. `{s}`" for i, s in enumerate(sources))
    await update.message.reply_text(
        f"📡 *قنوات المصدر ({len(sources)}):*\n{lines}", parse_mode="Markdown")


# ═══════════════════════════════════════════════════
# /setdest <id>   أو  /setdestme (داخل القناة)
# ═══════════════════════════════════════════════════
async def cmd_set_dest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    if not ctx.args:
        await update.message.reply_text(
            "📌 `/setdest -1001234567890`\n"
            "أو أضفني في القناة وأرسل `/setdestme`",
            parse_mode="Markdown")
        return
    ch = ctx.args[0].strip()
    db.set_setting("dest_channel", ch)
    await update.message.reply_text(f"✅ الهدف: `{ch}`", parse_mode="Markdown")

async def cmd_set_dest_me(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    chat_id = str(update.effective_chat.id)
    title   = getattr(update.effective_chat, "title", chat_id)
    db.set_setting("dest_channel", chat_id)
    await update.effective_message.reply_text(
        f"✅ *تم تعيين هذه القناة كهدف!*\n📛 {title}\n🆔 `{chat_id}`",
        parse_mode="Markdown")


# ═══════════════════════════════════════════════════
# /setfilter  — تحديد نوع المحتوى
# ═══════════════════════════════════════════════════
async def cmd_set_filter(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]

    if not ctx.args:
        flt     = db.get_filter()
        current = "الكل (بدون فلتر)" if not flt else ", ".join(flt)
        types_list = "\n".join(f"  `{t}` {TYPE_ICONS.get(t,'')}" for t in ALL_TYPES)
        await update.message.reply_text(
            f"🎚 *فلتر المحتوى الحالي:* {current}\n\n"
            f"*الأنواع المتاحة:*\n{types_list}\n\n"
            f"*أمثلة:*\n"
            f"`/setfilter video` — فيديو فقط\n"
            f"`/setfilter photo` — صور فقط\n"
            f"`/setfilter video photo` — فيديو وصور\n"
            f"`/setfilter audio voice` — صوتيات فقط\n"
            f"`/setfilter text` — نصوص فقط\n"
            f"`/clearfilter` — إلغاء الفلتر (كل شيء)",
            parse_mode="Markdown")
        return

    requested = [a.lower().strip() for a in ctx.args]
    valid   = [t for t in requested if t in ALL_TYPES]
    invalid = [t for t in requested if t not in ALL_TYPES]

    if not valid:
        await update.message.reply_text(
            f"❌ أنواع غير معروفة: {', '.join(invalid)}\n"
            f"الأنواع الصحيحة: {', '.join(ALL_TYPES)}",
            parse_mode="Markdown")
        return

    db.set_filter(valid)
    icons = " ".join(TYPE_ICONS.get(t,"") for t in valid)
    warn  = f"\n⚠️ تجاهل: {', '.join(invalid)}" if invalid else ""
    await update.message.reply_text(
        f"✅ *تم تعيين الفلتر:*\n"
        f"{icons} `{', '.join(valid)}`\n\n"
        f"البوت سينسخ *هذه الأنواع فقط*.{warn}",
        parse_mode="Markdown")


# ═══════════════════════════════════════════════════
# /clearfilter
# ═══════════════════════════════════════════════════
async def cmd_clear_filter(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    db.set_filter([])
    await update.message.reply_text(
        "✅ *تم إلغاء الفلتر — البوت سينسخ كل المحتوى.*", parse_mode="Markdown")


# ═══════════════════════════════════════════════════
# /copyarchive [max_id]
# ═══════════════════════════════════════════════════
async def cmd_copy_archive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database   = ctx.bot_data["db"]
    config: Config = ctx.bot_data["config"]

    if not is_admin(update.effective_user.id, config):
        await update.message.reply_text("⛔ ليس لديك صلاحية.")
        return

    sources = db.get_source_channels()
    dst     = db.get_dest_channel()
    flt     = db.get_filter()

    if not sources or not dst:
        await update.message.reply_text(
            "❌ لم تُعيَّن القنوات!\n"
            "استخدم `/addsource` و `/setdest`", parse_mode="Markdown")
        return

    if ctx.bot_data.get("archive_running"):
        await update.message.reply_text("⚠️ النسخ جارٍ بالفعل! أرسل `/stoparchive` لإيقافه.")
        return

    max_id = 50_000
    if ctx.args:
        try: max_id = int(ctx.args[0])
        except ValueError: pass

    flt_txt = "الكل" if not flt else " + ".join(TYPE_ICONS.get(t,"") + t for t in flt)
    src_lines = "\n".join(f"  • `{s}`" for s in sources)

    await update.message.reply_text(
        f"🚀 *بدأ النسخ السريع!*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📡 *المصادر ({len(sources)}):*\n{src_lines}\n"
        f"📥 *الهدف:* `{dst}`\n"
        f"🎚 *الفلتر:* {flt_txt}\n"
        f"🔢 *حتى ID:* `{max_id:,}`\n"
        f"⚡ *المعالجة المتوازية:* 15 طلب في آن واحد\n\n"
        f"ستصلك تقارير كل 500 رسالة.",
        parse_mode="Markdown")

    async def run():
        from app.archiver import copy_all_sources
        ctx.bot_data["archive_running"] = True
        try:
            await copy_all_sources(ctx.bot, db, update.effective_chat.id, max_id)
        finally:
            ctx.bot_data["archive_running"] = False

    asyncio.create_task(run())


# ═══════════════════════════════════════════════════
# /stoparchive
# ═══════════════════════════════════════════════════
async def cmd_stop_archive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.bot_data.get("archive_running"):
        ctx.bot_data["archive_running"] = False
        await update.message.reply_text("🛑 جارٍ إيقاف النسخ...")
    else:
        await update.message.reply_text("ℹ️ لا يوجد نسخ جارٍ.")


# ═══════════════════════════════════════════════════
# /status
# ═══════════════════════════════════════════════════
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    sources  = db.get_source_channels()
    dst      = db.get_dest_channel() or "❌ غير محددة"
    flt      = db.get_filter()
    archiving= "🔄 جارٍ" if ctx.bot_data.get("archive_running") else "⏸️ متوقف"
    flt_txt  = "الكل" if not flt else " + ".join(TYPE_ICONS.get(t,"") + t for t in flt)
    src_lines= "\n".join(f"  `{s}`" for s in sources) or "  ❌ لا توجد"

    await update.message.reply_text(
        f"📊 *حالة البوت*\n"
        f"━━━━━━━━━━━━━━\n"
        f"🟢 البوت: يعمل\n"
        f"📚 الأرشيف: {archiving}\n"
        f"🎚 الفلتر: {flt_txt}\n"
        f"📡 المصادر ({len(sources)}):\n{src_lines}\n"
        f"📥 الهدف: `{dst}`",
        parse_mode="Markdown")


# ═══════════════════════════════════════════════════
# /stats
# ═══════════════════════════════════════════════════
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    s = db.get_stats()
    type_lines = "".join(
        f"  {TYPE_ICONS.get(t,'📌')} {t}: *{c:,}*\n"
        for t, c in s.get("by_type", {}).items()
    ) or "  لا يوجد بيانات بعد"

    await update.message.reply_text(
        f"📈 *إحصائيات النسخ*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📦 الإجمالي: *{s['total']:,}*\n"
        f"📅 اليوم: *{s['today']:,}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"*التفصيل:*\n{type_lines}",
        parse_mode="Markdown")


# ═══════════════════════════════════════════════════
# /help
# ═══════════════════════════════════════════════════
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *دليل الاستخدام الكامل*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "*1️⃣ إضافة قنوات المصدر (يمكن أكثر من قناة):*\n"
        "أضف البوت مشرفاً في القناة ثم أرسل فيها:\n"
        "`/setsourceme` — لإضافتها مصدراً\n"
        "أو من الخاص: `/addsource -1001234567890`\n\n"
        "*2️⃣ تعيين القناة الهدف:*\n"
        "أضف البوت مشرفاً في القناة ثم:\n"
        "`/setdestme` — لتعيينها هدفاً\n\n"
        "*3️⃣ تحديد نوع المحتوى (اختياري):*\n"
        "`/setfilter video` — فيديو فقط\n"
        "`/setfilter photo video` — صور وفيديو\n"
        "`/setfilter audio voice` — صوتيات\n"
        "`/setfilter text` — نصوص فقط\n"
        "`/clearfilter` — كل شيء\n\n"
        "*4️⃣ نسخ الأرشيف الكامل:*\n"
        "`/copyarchive` — ينسخ كل الرسائل القديمة\n"
        "`/copyarchive 20000` — حتى ID محدد\n"
        "`/stoparchive` — إيقاف النسخ\n\n"
        "*5️⃣ المزامنة المباشرة:*\n"
        "تلقائية — كل رسالة جديدة تُنسخ فوراً\n\n"
        "*أوامر أخرى:*\n"
        "`/listsources` — عرض المصادر\n"
        "`/removesource <id>` — حذف مصدر\n"
        "`/status` /`/stats` /`/chatid`\n",
        parse_mode="Markdown")


# ═══════════════════════════════════════════════════
# معالج رسائل القنوات (مزامنة مباشرة)
# ═══════════════════════════════════════════════════
async def handle_channel_post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    msg = update.channel_post
    if not msg:
        return
    if msg.text and msg.text.startswith("/"):
        return

    sources = db.get_source_channels()
    dst     = db.get_dest_channel()
    if not sources or not dst:
        return

    chat_id  = str(msg.chat_id)
    username = f"@{msg.chat.username}" if msg.chat.username else None

    if chat_id not in sources and username not in sources:
        return

    if msg.media_group_id:
        logger.info(f"📦 ألبوم {msg.media_group_id} | {msg.message_id}")
        await handle_media_group_message(ctx.bot, msg, dst, db)
        return

    logger.info(f"📨 رسالة {msg.message_id} من {chat_id}")
    await copy_message_to_channel(ctx.bot, msg, dst, db)
