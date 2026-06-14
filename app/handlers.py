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
    src = db.get_setting("source_channel", "❌ غير محدد")
    dst = db.get_setting("dest_channel",   "❌ غير محدد")
    stats = db.get_stats()

    text = (
        "🤖 *بوت نسخ القنوات*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📡 *المصدر:* `{src}`\n"
        f"📥 *الهدف:* `{dst}`\n"
        f"📊 *الإجمالي:* {stats['total']:,} رسالة\n"
        f"📅 *اليوم:* {stats['today']:,} رسالة\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "*الأوامر:*\n"
        "/setsource — تعيين المصدر\n"
        "/setdest — تعيين الهدف\n"
        "/status — الحالة\n"
        "/stats — الإحصائيات\n"
        "/help — المساعدة\n\n"
        "📌 *لتعيين قناة خاصة:*\n"
        "أضفني مشرفاً في القناة ثم أرسل فيها:\n"
        "`/setsourceme` — لتعيينها مصدراً\n"
        "`/setdestme` — لتعيينها هدفاً\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─────────────────────────────────────────────
# /chatid — يظهر ID القناة أو المجموعة الحالية
# ─────────────────────────────────────────────
async def cmd_chatid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    chat_id = chat.id
    title = getattr(chat, "title", None) or "خاص"
    username = f"@{chat.username}" if getattr(chat, "username", None) else "لا يوجد"

    text = (
        f"🆔 *معرّف هذه القناة/المجموعة:*\n"
        f"`{chat_id}`\n\n"
        f"📛 الاسم: {title}\n"
        f"👤 المعرف: {username}\n\n"
        f"انسخ الرقم أعلاه واستخدمه مع:\n"
        f"`/setsource {chat_id}`\n"
        f"`/setdest {chat_id}`"
    )
    await msg.reply_text(text, parse_mode="Markdown")


# ─────────────────────────────────────────────
# /setsourceme — يُعيّن القناة الحالية كمصدر
# ─────────────────────────────────────────────
async def cmd_set_source_me(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    chat = update.effective_chat
    chat_id = str(chat.id)
    title = getattr(chat, "title", chat_id)

    db.set_setting("source_channel", chat_id)
    logger.info(f"📡 تعيين المصدر تلقائياً: {title} ({chat_id})")

    msg = update.effective_message
    if msg:
        await msg.reply_text(
            f"✅ *تم تعيين هذه القناة كمصدر!*\n"
            f"📛 {title}\n"
            f"🆔 `{chat_id}`",
            parse_mode="Markdown"
        )


# ─────────────────────────────────────────────
# /setdestme — يُعيّن القناة الحالية كهدف
# ─────────────────────────────────────────────
async def cmd_set_dest_me(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    chat = update.effective_chat
    chat_id = str(chat.id)
    title = getattr(chat, "title", chat_id)

    db.set_setting("dest_channel", chat_id)
    logger.info(f"📥 تعيين الهدف تلقائياً: {title} ({chat_id})")

    msg = update.effective_message
    if msg:
        await msg.reply_text(
            f"✅ *تم تعيين هذه القناة كهدف!*\n"
            f"📛 {title}\n"
            f"🆔 `{chat_id}`",
            parse_mode="Markdown"
        )


# ─────────────────────────────────────────────
# /setsource <channel_id>
# ─────────────────────────────────────────────
async def cmd_set_source(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    config: Config = ctx.bot_data["config"]

    if not is_admin(update.effective_user.id, config):
        await update.message.reply_text("⛔ ليس لديك صلاحية.")
        return

    if not ctx.args:
        await update.message.reply_text(
            "📌 *الاستخدام:*\n"
            "`/setsource -1001234567890`\n\n"
            "أو أضفني في القناة وأرسل فيها:\n"
            "`/setsourceme`",
            parse_mode="Markdown",
        )
        return

    channel = ctx.args[0].strip()
    db.set_setting("source_channel", channel)
    logger.info(f"📡 تم تعيين المصدر: {channel}")
    await update.message.reply_text(f"✅ تم تعيين القناة المصدر:\n`{channel}`", parse_mode="Markdown")


# ─────────────────────────────────────────────
# /setdest <channel_id>
# ─────────────────────────────────────────────
async def cmd_set_dest(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    config: Config = ctx.bot_data["config"]

    if not is_admin(update.effective_user.id, config):
        await update.message.reply_text("⛔ ليس لديك صلاحية.")
        return

    if not ctx.args:
        await update.message.reply_text(
            "📌 *الاستخدام:*\n"
            "`/setdest -1001234567890`\n\n"
            "أو أضفني في القناة وأرسل فيها:\n"
            "`/setdestme`",
            parse_mode="Markdown",
        )
        return

    channel = ctx.args[0].strip()
    db.set_setting("dest_channel", channel)
    logger.info(f"📥 تم تعيين الهدف: {channel}")
    await update.message.reply_text(f"✅ تم تعيين القناة الهدف:\n`{channel}`", parse_mode="Markdown")


# ─────────────────────────────────────────────
# /status
# ─────────────────────────────────────────────
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    src = db.get_setting("source_channel", "❌ غير محدد")
    dst = db.get_setting("dest_channel",   "❌ غير محدد")

    src_ok = "❌" not in src
    dst_ok = "❌" not in dst
    ready  = "🟢 يعمل" if (src_ok and dst_ok) else "🔴 يحتاج إعداد"

    await update.message.reply_text(
        f"📊 *حالة البوت*\n"
        f"━━━━━━━━━━━━━━\n"
        f"الحالة: {ready}\n"
        f"📡 المصدر: `{src}`\n"
        f"📥 الهدف: `{dst}`",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
# /stats
# ─────────────────────────────────────────────
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    stats = db.get_stats()
    await update.message.reply_text(
        f"📈 *إحصائيات النسخ*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📦 الإجمالي: *{stats['total']:,}* رسالة\n"
        f"📅 اليوم: *{stats['today']:,}* رسالة",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
# /help
# ─────────────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *دليل الاستخدام*\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "*الطريقة السهلة (قنوات خاصة):*\n"
        "1️⃣ أضفني مشرفاً في القناة المصدر\n"
        "2️⃣ أرسل في تلك القناة: `/setsourceme`\n"
        "3️⃣ أضفني مشرفاً في القناة الهدف\n"
        "4️⃣ أرسل في تلك القناة: `/setdestme`\n"
        "5️⃣ البوت يعمل تلقائياً! 🚀\n\n"
        "*الطريقة اليدوية (إذا عرفت الـ ID):*\n"
        "`/setsource -1001234567890`\n"
        "`/setdest -1001234567891`\n\n"
        "*معرفة ID أي قناة:*\n"
        "أضفني فيها وأرسل: `/chatid`\n\n"
        "*الوسائط المدعومة:*\n"
        "🖼 صور | 🎥 فيديو | 🎵 صوت\n"
        "🎤 رسائل صوتية | 📄 ملفات | 🎭 ملصقات\n",
        parse_mode="Markdown",
    )


# ─────────────────────────────────────────────
# معالج رسائل القنوات
# ─────────────────────────────────────────────
async def handle_channel_post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    msg = update.channel_post
    if not msg:
        return

    # تجاهل أوامر التعيين (تُعالَج بشكل منفصل)
    if msg.text and msg.text.startswith("/"):
        return

    source_channel = db.get_setting("source_channel")
    dest_channel   = db.get_setting("dest_channel")

    if not source_channel or not dest_channel:
        return

    chat_id  = str(msg.chat_id)
    username = f"@{msg.chat.username}" if msg.chat.username else None

    is_source = (chat_id == source_channel) or (username and username == source_channel)
    if not is_source:
        return

    logger.info(f"📨 رسالة جديدة {msg.message_id} من {chat_id}")
    await copy_message_to_channel(ctx.bot, msg, dest_channel, db)
