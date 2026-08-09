# نشر منصة الفريج على Netlify وGitHub

## القرار الحالي

الريبو خاص، وهذا هو الاختيار الصحيح لحماية مفاتيح المشروع والكود. لذلك:

- GitHub Pages لا يعمل للريبو الخاص على الخطة الحالية.
- النشر العام المناسب الآن هو Netlify مع بقاء الريبو خاصًا.
- الواجهة فقط تنشر كملفات static من `frontend/`.
- الباك إند Python يحتاج عنوان API مستقل تضبطه في `ALFORAIJ_API_BASE`.

## المطلوب في GitHub Actions

من:

`Settings -> Secrets and variables -> Actions`

أضف Variable واحدًا:

```text
ALFORAIJ_API_BASE=https://your-backend-domain.example.com
```

وأضف Secretين للنشر على Netlify:

```text
NETLIFY_AUTH_TOKEN
NETLIFY_SITE_ID
```

بدون هذين السرّين سيفشل Workflow النشر عمدًا برسالة واضحة، حتى لا يظهر نجاح وهمي بدون رابط منشور.

## مفاتيح الباك إند والتحديث اليومي

هذه تبقى Secrets ولا توضع أبدًا في الواجهة:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
AGENT_ROUTER_API_KEY
OFFICIAL_TRANSACTIONS_SOURCE
```

`OFFICIAL_TRANSACTIONS_SOURCE` يمكن أن يكون ملف CSV/JSON داخل المشروع أو رابط CSV/JSON رسمي. وكيل التحديث اليومي يقرأه تلقائيًا عند التشغيل المجدول.

## Workflows

- `deploy-static.yml`: يبني الواجهة، يضبط `frontend/config.js`، وينشر على Netlify عند وجود الأسرار.
- `daily-data-update.yml`: يشغل وكيل تحديث البيانات يوميًا الساعة 06:00 بتوقيت القاهرة.

## ملاحظات تشغيل

- لا تضع `SUPABASE_SERVICE_ROLE_KEY` في `frontend/config.js`.
- GitHub Pages سيظل متوقفًا طالما الريبو خاص والخطة لا تدعمه.
- عند توفير Netlify secrets يمكن تشغيل `Deploy static frontend` يدويًا من تبويب Actions.
