# تفعيل تسجيل الدخول بـ Google — خطوات تفصيلية

## الخطوة 1: إنشاء مشروع Google Cloud

1. اذهب إلى [console.cloud.google.com](https://console.cloud.google.com)
2. أنشئ مشروع جديد أو اختر مشروع موجود
3. اسم المشروع: `alforaij-platform` (أو أي اسم تفضله)

## الخطوة 2: تفعيل Google Identity Services API

1. في Console، اذهب إلى **APIs & Services** → **Library**
2. ابحث عن **Google Identity Services**
3. اضغط **Enable**

## الخطوة 3: إنشاء OAuth 2.0 Client ID

1. اذهب إلى **APIs & Services** → **Credentials**
2. اضغط **Create Credentials** → **OAuth client ID**
3. اختر **Web application** كنوع التطبيق
4. أضف **Authorized JavaScript origins**:
   - `http://127.0.0.1:8000` (للتطوير المحلي)
   - `https://your-domain.com` (للإنتاج)
5. احفظ وانسخ **Client ID**

## الخطوة 4: تفعيل Client ID

### الخيار A: متغير بيئة (مُوصى به)

```bash
# Windows PowerShell
$env:GOOGLE_CLIENT_ID = "YOUR_CLIENT_ID.apps.googleusercontent.com"

# أو أضفه في ملف .env
echo "GOOGLE_CLIENT_ID=YOUR_CLIENT_ID.apps.googleusercontent.com" > .env
```

### الخيار B: في ملف config.js

```javascript
// frontend/config.js
window.GOOGLE_CLIENT_ID = "YOUR_CLIENT_ID.apps.googleusercontent.com";
```

## الخطوة 5: التشغيل والاختبار

1. أعد تشغيل الخادم:
   ```bash
   cd alforaij-research-assistant
   python -m backend.main
   ```

2. افتح المتصفح على `http://127.0.0.1:8000`

3. اضغط "حساب" → "الدخول بحساب Google"

4. يجب أن تظهر نافذة تسجيل الدخول من Google

## ملاحظات مهمة

- **Client ID آمن للمشاركة** — ليس سرًا
- **Redirect URIs** غير مطلوبة لـ GIS (الكود يعمل من المتصفح مباشرة)
- **المختبر**: استخدم `http://127.0.0.1:8000` فقط في الإنتاج
- **الإنتاج**: أضف نطاق موقعك في Authorized JavaScript origins

## استكشاف الأخطاء

| المشكلة | الحل |
|---------|------|
| "غير متاح حاليًا" | تأكد أن `GOOGLE_CLIENT_ID` مُعرّف |
| "خطأ في الاتصال" | تحقق من أن الخادم يعمل |
| "بيانات Google غير صالحة" | تأكد من أن Client ID صحيح |
| النافذة لا تظهر | تحقق من تحميل Google GIS script |
