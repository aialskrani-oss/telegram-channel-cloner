# 🤖 Telegram Channel Cloner — نظام نسخ القنوات الاحترافي

نظام متكامل واحترافي لنسخ محتوى قنوات تيليجرام تلقائياً مع المزامنة الفورية.

---

## ✨ المميزات

| الميزة | الوصف |
|--------|-------|
| 📚 نسخ الأرشيف الكامل | نسخ جميع الرسائل السابقة بالترتيب |
| 🔴 مزامنة مباشرة | نسخ الرسائل الجديدة فور وصولها |
| 📸 دعم جميع أنواع الوسائط | صور، فيديو، مستندات، صوت، ملصقات |
| 🔄 استئناف تلقائي | يستأنف من حيث توقف بعد الأعطال |
| 🚫 منع التكرار | لا يُعاد نسخ رسالة مرتين |
| 📊 إحصائيات مفصّلة | تتبع دقيق لحالة كل رسالة |
| ⚡ معالجة الأخطاء | إعادة محاولة تلقائية مع FloodWait |
| 💾 SQLite للحالة | تتبع مستمر لا يضيع |

---

## 🚀 التشغيل السريع

### 1. الحصول على بيانات API

1. توجّه إلى [my.telegram.org](https://my.telegram.org)
2. اضغط على **API development tools**
3. أنشئ تطبيقاً جديداً
4. احفظ `API_ID` و `API_HASH`

### 2. إعداد ملف البيئة

```bash
cp .env.example .env
# عدّل الملف وأضف بياناتك
```

### 3. توليد SESSION_STRING (مرة واحدة فقط)

```bash
pip install -r requirements.txt
python -m app.main
# اتبع التعليمات لإدخال رقم هاتفك ورمز التحقق
# انسخ SESSION_STRING الناتج وأضفه إلى .env
```

### 4. التشغيل

```bash
python -m app.main
```

---

## 🐳 التشغيل بـ Docker

```bash
docker build -t telegram-cloner .
docker run -d \
  --name telegram-cloner \
  --env-file .env \
  -v $(pwd)/data:/data \
  --restart unless-stopped \
  telegram-cloner
```

---

## ☁️ النشر على Render

### النشر التلقائي

```bash
# تعيين المتغيرات
export GITHUB_TOKEN=your_github_token
export GITHUB_USERNAME=your_github_username
export RENDER_API_KEY=your_render_api_key

# رفع على GitHub
python setup_github.py

# النشر على Render
python deploy_render.py
```

---

## ⚙️ متغيرات البيئة

| المتغير | مطلوب | الوصف |
|---------|-------|-------|
| `API_ID` | ✅ | معرّف تطبيق تيليجرام |
| `API_HASH` | ✅ | مفتاح تطبيق تيليجرام |
| `SESSION_STRING` | ✅ | جلسة تيليجرام (Telethon) |
| `SOURCE_CHANNEL` | ✅ | معرّف القناة المصدر |
| `DESTINATION_CHANNEL` | ✅ | معرّف القناة الهدف |
| `BATCH_SIZE` | ❌ | حجم الدفعة (افتراضي: 50) |
| `DELAY_BETWEEN_MESSAGES` | ❌ | تأخير بين الرسائل بالثواني (0.5) |
| `DELAY_BETWEEN_BATCHES` | ❌ | تأخير بين الدفعات بالثواني (2.0) |
| `MAX_RETRIES` | ❌ | أقصى عدد محاولات (5) |
| `RETRY_DELAY` | ❌ | تأخير إعادة المحاولة (10.0) |
| `DB_PATH` | ❌ | مسار قاعدة البيانات (/data/cloner.db) |

---

## 📁 هيكل المشروع

```
telegram-cloner/
├── app/
│   ├── main.py      — نقطة الدخول الرئيسية
│   ├── config.py    — إدارة الإعدادات
│   ├── sync.py      — منطق المزامنة
│   ├── copier.py    — نسخ الرسائل والوسائط
│   ├── database.py  — إدارة قاعدة البيانات
│   └── logger.py    — نظام التسجيل
├── data/            — قاعدة البيانات والسجلات (مُركّبة)
├── requirements.txt
├── Dockerfile
├── render.yaml
├── setup_github.py
├── deploy_render.py
├── .env.example
└── README.md
```

---

## 📄 الترخيص

MIT License — مجاني للاستخدام الشخصي والتجاري.
