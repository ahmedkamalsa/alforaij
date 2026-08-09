# نشر منصة الفريج على GitHub Pages وNetlify وCloudflare

## القرار الحالي

بعد الموافقة على جعل الريبو عامًا، يصبح GitHub Pages هو مسار النشر الأساسي للواجهة.

- GitHub Pages يعمل عند جعل الريبو public.
- Netlify مسار احتياطي، لكنه يحتاج `NETLIFY_AUTH_TOKEN` و`NETLIFY_SITE_ID`، وحساب Netlify الحالي لديه production deploys متوقفة بسبب credits.
- Cloudflare Pages مسار احتياطي جيد، ويحتاج `CLOUDFLARE_API_TOKEN` و`CLOUDFLARE_ACCOUNT_ID`.
- الواجهة فقط تنشر كملفات static من `frontend/`.
- الباك إند Python يحتاج عنوان API مستقل تضبطه في `ALFORAIJ_API_BASE`.

## المطلوب في GitHub Actions

من:

`Settings -> Secrets and variables -> Actions`

أضف Variable واحدًا:

```text
ALFORAIJ_API_BASE=https://your-backend-domain.example.com
```

أسرار Netlify الاختيارية:

```text
NETLIFY_AUTH_TOKEN
NETLIFY_SITE_ID
```

أسرار Cloudflare الاختيارية:

```text
CLOUDFLARE_API_TOKEN
CLOUDFLARE_ACCOUNT_ID
```

ومتغير Cloudflare الاختياري:

```text
CLOUDFLARE_PAGES_PROJECT_NAME=alforaij
```

بدون أسرار Netlify أو Cloudflare سيظهر تحذير فقط. GitHub Pages يبقى المسار الأساسي بعد جعل الريبو public.

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

- `deploy-static.yml`: يبني الواجهة، يضبط `frontend/config.js`، وينشر على GitHub Pages، ويحاول Netlify عند وجود أسراره.
- `deploy-cloudflare-pages.yml`: ينشر على Cloudflare Pages عند وجود أسرار Cloudflare.
- `daily-data-update.yml`: يشغل وكيل تحديث البيانات يوميًا الساعة 06:00 بتوقيت القاهرة.

## ملاحظات تشغيل

- لا تضع `SUPABASE_SERVICE_ROLE_KEY` في `frontend/config.js`.
- لا تجعل أي مفاتيح سرية داخل ملفات `frontend/`.
- عند توفير Netlify أو Cloudflare secrets يمكن تشغيل workflow الخاص يدويًا من تبويب Actions.
