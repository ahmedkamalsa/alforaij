# نشر منصة الفريج على Netlify وGitHub Pages

## الفكرة

الواجهة `frontend/` تنشر كنسخة static على Netlify وGitHub Pages.
الباك إند Python يبقى API مستقلًا، والواجهة تتصل به عبر:

```js
window.ALFORAIJ_API_BASE
```

محليًا يظل فارغًا ويستخدم نفس النطاق:

```text
http://127.0.0.1:8000
```

## GitHub Actions Variables

من GitHub repo:

`Settings -> Secrets and variables -> Actions -> Variables`

أضف:

```text
ALFORAIJ_API_BASE=https://your-backend-domain.example.com
OFFICIAL_TRANSACTIONS_SOURCE=data/moj_transactions.csv
```

`ALFORAIJ_API_BASE` ليس سرًا. هو عنوان API الذي ستتصل به واجهة Netlify/GitHub Pages.

## GitHub Actions Secrets

من:

`Settings -> Secrets and variables -> Actions -> Secrets`

أضف:

```text
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
AGENT_ROUTER_API_KEY
NETLIFY_AUTH_TOKEN
NETLIFY_SITE_ID
```

`NETLIFY_AUTH_TOKEN` و`NETLIFY_SITE_ID` مطلوبان فقط لو تريد نشر Netlify من GitHub Actions.

## Workflows

- `.github/workflows/deploy-static.yml`
  - ينشر `frontend/` على GitHub Pages.
  - ينشر Netlify إذا كانت أسرار Netlify موجودة.
  - ينشئ `frontend/config.js` تلقائيًا بقيمة `ALFORAIJ_API_BASE`.

- `.github/workflows/daily-data-update.yml`
  - يعمل يوميًا 06:00 بتوقيت القاهرة.
  - يشغل وكيل التحديث اليومي.
  - يحدث Supabase والفرص والإشعارات.

## شاشة التشغيل داخل المنصة

من نفس الواجهة:

- ارفع CSV/JSON لصفقات وزارة العدل.
- اضغط `استيراد الصفقات`.
- سيحفظها في `official_transactions`.
- سيشغل الوكيل لإعادة بناء الفرص.

الاستيراد اليدوي من الواجهة ليس المسار الوحيد. وكيل التحديث اليومي يستورد تلقائيًا من:

```text
OFFICIAL_TRANSACTIONS_SOURCE
```

إذا كانت القيمة ملفًا داخل المشروع أو رابط CSV/JSON. الرفع من الواجهة يستخدم فقط عندما يصل ملف جديد وتريد إدخاله فورًا بدون انتظار التشغيل المجدول.

## ملاحظات مهمة

- GitHub Pages وNetlify لا يشغلان باك إند Python مباشرة.
- لذلك يجب توفير API backend مستقر وضبط `ALFORAIJ_API_BASE`.
- لا تضع `SUPABASE_SERVICE_ROLE_KEY` في الواجهة أو `config.js`.
- الصفقات الرسمية لا تدخل التقييم إلا بعد استيراد CSV/JSON منظم وموثق.
