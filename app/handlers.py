import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from app.database import Database
from app.config import Config
from app.copier import copy_message_to_channel
from app.logger import logger


def is_admin(user_id: int, config: Config) -> bool:
    return not config.admin_ids or user_id in config.admin_ids


# ─────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    src   = db.get_setting("source_channel", "❌ غير محدد")
    dst   = db.get_setting("dest_channel",   "❌ غير محدد")
    stats = db.get_stats()

    await update.message.reply_text(
        "🤖 *بوت نسخ القنوات*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📡 *المصدر:* `{src}`\n"
        f"📥 *الهدف:* `{dst}`\n"
        f"📊 *الإجمالي:* {stats['total']:,} رسالة\n"
        f"📅 *اليوم:* {stats['today']:,} رسالة\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "*الأوامر الرئيسية:*\n"
        "/setsource — تعيين المصدر\n"
        "/setdest — تعيين الهدف\n"
        "/copyarchive — نسخ الأرشيف الكامل 🆕\n"
        "/status — الحالة\n"
        "/stats — الإحصائيات\n"
        "/help — المساعدة\n\n"
        "📌 *للقنوات الخاصة أضفني ثم أرسل:*\n"
        "`/setsourceme` أو `/setdestme`",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
# /chatid
# ─────────────────────────────────────────────
async def cmd_chatid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    await update.effective_message.reply_text(
        f"🆔 *معرّف هذه القناة:*\n"
        f"`{chat.id}`\n\n"
        f"📛 الاسم: {getattr(chat,'title','-')}\n"
        f"👤 المعرف: {'@'+chat.username if getattr(chat,'username',None) else 'خاص'}\n\n"
        f"استخدمه مع:\n"
        f"`/setsource {chat.id}`\n"
        f"`/setdest {chat.id}`",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
# /setsourceme  (داخل القناة)
# ─────────────────────────────────────────────
async def cmd_set_source_me(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    chat = update.effective_chat
    chat_id = str(chat.id)
    db.set_setting("source_channel", chat_id)
    logger.info(f"📡 مصدر جديد: {getattr(chat,'title',chat_id)} ({chat_id})")
    await update.effective_message.reply_text(
        f"✅ *تم تعيين هذه القناة كمصدر!*\n`{chat_id}`",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
# /setdestme  (داخل القناة)
# ─────────────────────────────────────────────
async def cmd_set_dest_me(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    chat = update.effective_chat
    chat_id = str(chat.id)
    db.set_setting("dest_channel", chat_id)
    logger.info(f"📥 هدف جديد: {getattr(chat,'title',chat_id)} ({chat_id})")
    await update.effective_message.reply_text(
        f"✅ *تم تعيين هذه القناة كهدف!*\n`{chat_id}`",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
# /setsource <id>
# ─────────────────────────────────────────────
async def cmd_set_source(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    if not ctx.args:
        await update.message.reply_text(
            "📌 `/setsource -1001234567890`\n"
            "أو أرسل `/setsourceme` داخل القناة.",
            parse_mode="Markdown",
        )
        return
    ch = ctx.args[0].strip()
    db.set_setting("source_channel", ch)
    await update.message.reply_text(f"✅ المصدر: `{ch}`", parse_mode="Markdown")


# ─────────────────────────────────────────────
# /setdest <id>
# ─────────────────────────────────────────────
async def cmd_set_dest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    if not ctx.args:
        await update.message.reply_text(
            "📌 `/setdest -1001234567890`\n"
            "أو أرسل `/setdestme` داخل القناة.",
            parse_mode="Markdown",
        )
        return
    ch = ctx.args[0].strip()
    db.set_setting("dest_channel", ch)
    await update.message.reply_text(f"✅ الهدف: `{ch}`", parse_mode="Markdown")


# ─────────────────────────────────────────────
# /copyarchive — نسخ الأرشيف الكامل
# ─────────────────────────────────────────────
async def cmd_copy_archive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database     = ctx.bot_data["db"]
    config: Config   = ctx.bot_data["config"]
    user_id = update.effective_user.id

    if not is_admin(user_id, config):
        await update.message.reply_text("⛔ ليس لديك صلاحية.")
        return

    src = db.get_setting("source_channel")
    dst = db.get_setting("dest_channel")

    if not src or not dst:
        await update.message.reply_text(
            "❌ لم تُعيَّن القنوات بعد!\n"
            "أرسل `/setsourceme` في المصدر و `/setdestme` في الهدف.",
            parse_mode="Markdown",
        )
        return

    # هل يعمل بالفعل؟
    if ctx.bot_data.get("archive_running"):
        await update.message.reply_text("⚠️ نسخ الأرشيف جارٍ بالفعل! انتظر حتى ينتهي.")
        return

    # حد أقصى مخصص؟
    max_id = 50000
    if ctx.args:
        try:
            max_id = int(ctx.args[0])
        except ValueError:
            pass

    await update.message.reply_text(
        f"🚀 *بدأ نسخ الأرشيف!*\n"
        f"📡 المصدر: `{src}`\n"
        f"📥 الهدف: `{dst}`\n"
        f"🔢 حتى ID: `{max_id}`\n\n"
        f"ستصلك تقارير تقدم كل 200 رسالة.",
        parse_mode="Markdown",
    )

    # تشغيل في الخلفية
    async def run_archive():
        from app.archiver import copy_archive
        ctx.bot_data["archive_running"] = True
        try:
            await copy_archive(
                bot=ctx.bot,
                source_channel=src,
                dest_channel=dst,
                db=db,
                status_chat_id=update.effective_chat.id,
                max_id=max_id,
            )
        finally:
            ctx.bot_data["archive_running"] = False

    asyncio.create_task(run_archive())


# ─────────────────────────────────────────────
# /stoparchive — إيقاف النسخ
# ─────────────────────────────────────────────
async def cmd_stop_archive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.bot_data.get("archive_running"):
        ctx.bot_data["archive_running"] = False
        await update.message.reply_text("🛑 جارٍ إيقاف النسخ...")
    else:
        await update.message.reply_text("ℹ️ لا يوجد نسخ جارٍ حالياً.")


# ─────────────────────────────────────────────
# /status
# ─────────────────────────────────────────────
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    src = db.get_setting("source_channel", "❌ غير محدد")
    dst = db.get_setting("dest_channel",   "❌ غير محدد")
    archiving = "🔄 جارٍ" if ctx.bot_data.get("archive_running") else "⏸️ متوقف"

    await update.message.reply_text(
        f"📊 *حالة البوت*\n"
        f"━━━━━━━━━━━━━━\n"
        f"📡 المصدر: `{src}`\n"
        f"📥 الهدف: `{dst}`\n"
        f"📚 نسخ الأرشيف: {archiving}\n"
        f"🟢 البوت: يعمل",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
# /stats
# ─────────────────────────────────────────────
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    s = db.get_stats()

    type_icons = {
        "photo": "🖼", "video": "🎥", "audio": "🎵",
        "voice": "🎤", "document": "📄", "sticker": "🎭",
        "animation": "🎞", "text": "💬", "video_note": "📹",
        "unknown": "❓",
    }
    type_lines = ""
    for t, count in s.get("by_type", {}).items():
        icon = type_icons.get(t, "📌")
        type_lines += f"  {icon} {t}: *{count:,}*\n"

    await update.message.reply_text(
        f"📈 *إحصائيات النسخ*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📦 الإجمالي: *{s['total']:,}* رسالة\n"
        f"📅 اليوم: *{s['today']:,}* رسالة\n"
        f"━━━━━━━━━━━━━━━\n"
        f"*التفصيل حسب النوع:*\n"
        f"{type_lines if type_lines else '  لا يوجد بيانات بعد'}",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
# /help
# ─────────────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *دليل الاستخدام*\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "*🔧 إعداد القنوات:*\n"
        "أضف البوت مشرفاً في القناتين، ثم:\n"
        "`/setsourceme` — في قناة المصدر\n"
        "`/setdestme` — في قناة الهدف\n\n"
        "*📚 نسخ الأرشيف القديم:*\n"
        "`/copyarchive` — يبدأ نسخ كل الرسائل\n"
        "`/copyarchive 10000` — حتى ID محدد\n"
        "`/stoparchive` — إيقاف النسخ\n\n"
        "*📡 مزامنة مباشرة:*\n"
        "تلقائية — كل رسالة جديدة تُنسخ فوراً\n\n"
        "*ℹ️ أوامر أخرى:*\n"
        "`/status` — الحالة\n"
        "`/stats` — الإحصائيات\n"
        "`/chatid` — معرف القناة الحالية\n",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
# معالج رسائل القنوات (مزامنة مباشرة)
# ─────────────────────────────────────────────
async def handle_channel_post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    msg = update.channel_post
    if not msg:
        return

    if msg.text and msg.text.startswith("/"):
        return

    src = db.get_setting("source_channel")
    dst = db.get_setting("dest_channel")
    if not src or not dst:
        return

    chat_id  = str(msg.chat_id)
    username = f"@{msg.chat.username}" if msg.chat.username else None
    if chat_id != src and username != src:
        return

    logger.info(f"📨 رسالة جديدة {msg.message_id} من {chat_id}")
    await copy_message_to_channel(ctx.bot, msg, dst, db)
