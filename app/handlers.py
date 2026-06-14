from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
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
    src = db.get_setting("source_channel", "غير محدد")
    dst = db.get_setting("dest_channel", "غير محدد")
    stats = db.get_stats()

    text = (
        "🤖 *بوت نسخ القنوات*\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"📡 *القناة المصدر:* `{src}`\n"
        f"📥 *القناة الهدف:* `{dst}`\n"
        f"📊 *إجمالي المنسوخ:* {stats['total']:,} رسالة\n"
        f"📅 *اليوم:* {stats['today']:,} رسالة\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "الأوامر المتاحة:\n"
        "/setsource — تعيين القناة المصدر\n"
        "/setdest — تعيين القناة الهدف\n"
        "/status — عرض الحالة\n"
        "/stats — الإحصائيات\n"
        "/help — المساعدة\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


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
            "📌 *كيفية الاستخدام:*\n"
            "`/setsource @username` أو\n"
            "`/setsource -1001234567890`",
            parse_mode="Markdown",
        )
        return

    channel = ctx.args[0].strip()
    db.set_setting("source_channel", channel)
    logger.info(f"📡 تم تعيين القناة المصدر: {channel}")
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
            "📌 *كيفية الاستخدام:*\n"
            "`/setdest @username` أو\n"
            "`/setdest -1001234567890`",
            parse_mode="Markdown",
        )
        return

    channel = ctx.args[0].strip()
    db.set_setting("dest_channel", channel)
    logger.info(f"📥 تم تعيين القناة الهدف: {channel}")
    await update.message.reply_text(f"✅ تم تعيين القناة الهدف:\n`{channel}`", parse_mode="Markdown")


# ─────────────────────────────────────────────
# /status
# ─────────────────────────────────────────────
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    src = db.get_setting("source_channel", "❌ غير محدد")
    dst = db.get_setting("dest_channel", "❌ غير محدد")

    src_ok = src != "❌ غير محدد"
    dst_ok = dst != "❌ غير محدد"
    ready = "🟢 يعمل" if (src_ok and dst_ok) else "🔴 يحتاج إعداد"

    text = (
        f"📊 *حالة البوت*\n"
        f"━━━━━━━━━━━━━━\n"
        f"الحالة: {ready}\n"
        f"📡 المصدر: `{src}`\n"
        f"📥 الهدف: `{dst}`\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─────────────────────────────────────────────
# /stats
# ─────────────────────────────────────────────
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    stats = db.get_stats()
    text = (
        f"📈 *إحصائيات النسخ*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📦 الإجمالي: *{stats['total']:,}* رسالة\n"
        f"📅 اليوم: *{stats['today']:,}* رسالة\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─────────────────────────────────────────────
# /help
# ─────────────────────────────────────────────
async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *دليل الاستخدام*\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "*1️⃣ أضف البوت مشرفاً في القناتين*\n"
        "— القناة المصدر: صلاحية قراءة الرسائل\n"
        "— القناة الهدف: صلاحية نشر الرسائل\n\n"
        "*2️⃣ حدد القنوات*\n"
        "`/setsource @source_channel`\n"
        "`/setdest @dest_channel`\n\n"
        "*3️⃣ البوت يعمل تلقائياً!*\n"
        "كل رسالة جديدة في المصدر تُنسخ فوراً للهدف\n\n"
        "*الوسائط المدعومة:*\n"
        "🖼 صور | 🎥 فيديو | 🎵 صوت | 🎤 رسائل صوتية\n"
        "📄 ملفات | 🎭 ملصقات | 🎞 GIF | 📊 استطلاعات\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─────────────────────────────────────────────
# معالج الرسائل من القنوات
# ─────────────────────────────────────────────
async def handle_channel_post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db: Database = ctx.bot_data["db"]
    msg = update.channel_post or update.message
    if not msg:
        return

    source_channel = db.get_setting("source_channel")
    dest_channel = db.get_setting("dest_channel")

    if not source_channel or not dest_channel:
        return

    chat_id = str(msg.chat_id)
    chat_username = f"@{msg.chat.username}" if msg.chat.username else None

    is_source = (chat_id == source_channel or chat_username == source_channel)
    if not is_source:
        return

    logger.info(f"📨 رسالة جديدة {msg.message_id} من {chat_id}")
    await copy_message_to_channel(ctx.bot, msg, dest_channel, db)
