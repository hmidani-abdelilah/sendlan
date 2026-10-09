# SendLan

## العربية / Arabic

SendLan هو تطبيق مراسلة محلية داخل الشبكة المحلية (LAN)، ويستهدف تبادل الرسائل والملفات بين الأجهزة القريبة. التطبيق الأساسي يبقى كما هو للكمبيوتر، أما نسخة الهاتف فتم إعدادها بشكل منفصل داخل مجلد `android/` باستخدام Flet.

### التشغيل على الكمبيوتر

```bash
python main.py
```

### بناء نسخة Android داخل مجلد `android`

```bash
cd /home/xq/sendlan
flet build apk android -o android/build
```

هذا الأمر يبني تطبيق Android باستخدام الملف الرئيسي داخل مجلد `android/` ويضع النتيجة داخل `android/build/`.

ملاحظة فنية: تم تثبيت توافق Flutter/Flet عبر `android/pyproject.toml` بحيث يلتزم مشروع Android بـ `jni ^1.1.0` لتجنب خطأ `package:jni ^1.1.0` أثناء الإنشاء.

### ملاحظة مهمة

- التطبيق الرئيسي desktop لا يزال يعمل من `main.py`
- نسخة الهاتف مستقلة داخل مجلد `android/`
- يستخدم ملف الصوت `assets/notification.wav` للتنبيه عند وصول رسائل الدردشة في نسخة desktop والهاتف
- يجب على المستقبل قبول الملف أو رفضه؛ يُلغى الطلب تلقائيًا إذا لم يصل رد خلال 30 ثانية

---

## English

SendLan is a local messaging app for devices on the same LAN. The desktop app remains unchanged, while the phone version is prepared separately under the `android/` folder using Flet.

### Run on desktop

```bash
python main.py
```

### Build the Android version inside the `android` folder

```bash
cd /home/xq/sendlan
flet build apk android -o android/build
```

This command builds the Android app using the `android/main.py` entry point and writes the output under `android/build/`.

Technical note: the project pins `jni ^1.1.0` in `android/pyproject.toml` so the generated Flutter app avoids the `package:jni ^1.1.0` version mismatch during APK builds.

### Important note

- The desktop app remains in `main.py`
- The mobile version is kept in the `android/` folder
- The `assets/notification.wav` sound plays when chat messages arrive in both desktop and mobile apps
- The recipient must accept or reject incoming files; unanswered requests expire after 30 seconds

## Project structure

```text
sendlan/
├── main.py                     # desktop app
├── README.md
├── requirements.txt
├── assets/
│   ├── icon.png
│   └── notification.wav
├── src/
│   └── sendlan/
│       ├── flet_app.py
│       └── ...
├── android/
│   ├── main.py                # Android/Flet app entry
│   └── README.md
└── android/build/             # APK output directory after build
```