# الدليل الشامل لمشاريع الفريج وهيرمس

آخر تحديث: 2026-09-16

هذا الملف هو نقطة البداية لأي مستخدم أو مطور أو Agent جديد.

## الخلاصة السريعة

| المجال | مجلد التوجيه | الريبو الحقيقي | الاستخدام |
|---|---|---|---|
| بحث الفريج والمنصة الذكية | `01_ALFORAIJ_PLATFORM/` | `alforaij-research-assistant/` | البحث، API، التحليل، بيانات الفريج الحية، GitHub Pages |
| لوحة الفريج والأرقام | `02_ALFORAIJBOARD_DASHBOARD/` | `vs/` ثم `alforaijboard/` حسب الهدف | Netlify الحالي أقربه `vs/site` |
| هيرمس والتشغيل المحلي | `03_HERMES_OPS/` | `hermes-ops/` | Hermes Pro، routing، health registry |

## أين أبدأ؟

1. تحديث بحث الفريج أو الأرقام الحية من API الأصلي: `alforaij-research-assistant/`.
2. إصلاح `https://alforaijboard.netlify.app/`: `vs/site`.
3. تشغيل Hermes أو تعديل routing/model/provider: `hermes-ops/`.
4. لا تنقل الريبو نفسه قبل تعديل workflows والمسارات.

## حالة النشر الحالية

الرابط المؤكد بعد آخر إصلاح:

`https://ahmedkamalsa.github.io/alforaijboard/`

تم اختباره ويعرض:

`البيانات: 1320 إعلان مباشر من القاعدة (الفريج 320 + المواقع الخارجية 1000)`

آخر commit في `alforaij-research-assistant`:

`b787454 fix: refresh alforaij live count in static frontend`

## Netlify

الرابط:

`https://alforaijboard.netlify.app/`

ما زال يظهر رقم 182 لأن الموقع الحالي على Netlify غير مربوط تلقائيًا بآخر `git push`، وأقرب مصدر محلي له هو:

`vs/site/index.html`

الحالة المحلية الحالية داخل `vs/site/index.html` أحدث من المنشور وتحتوي:

- إجمالي سجلات: `313`
- حركة الدلال: `313`
- عروض للبيع: `220`
- طلبات شراء: `38`
- عروض الإيجار: `50`
- طلبات الإيجار: `5`

لكن لم يتم نشرها على Netlify لأن البيئة الحالية لا تحتوي `NETLIFY_AUTH_TOKEN` أو `NETLIFY_SITE_ID` كمتغيرات نظام، ولا يوجد `.netlify/state.json`.

## لماذا لم يظهر التغيير على Netlify؟

الإصلاح السابق نشر عبر GitHub Actions إلى GitHub Pages. أما Netlify الحالي يخدم نسخة مستقلة قديمة. لذلك رؤية `182` في Netlify تعني أن Netlify يحتاج deploy مباشر من `vs/site` أو إعادة ربطه بالمصدر الصحيح.

## قاعدة أمان

- لا تطبع secrets أو tokens.
- لا تضف `.env` إلى git.
- لا تنشر Netlify يدويًا إلا بعد التأكد أن artifact هو `vs/site`.
- لا تستخدم `git reset --hard` لتنظيف تغييرات غير مفهومة.

## تنظيف تم

تم أرشفة مجلدات مؤقتة إلى:

`_archive/cleanup-20260916-1115/`

تمت أرشفة:

- `.tmp-npm-cache-netlify`
- `_deploy_alforaijboard_gh_pages_20260916`

لم يتم نقل `.tmp_alforaijboard_build_check_20260914` لأن النقل فشل بسبب صلاحيات/ملفات مقفولة، ولم يتم حذفه.

## الملفات التفصيلية

- بحث الفريج: `01_ALFORAIJ_PLATFORM/README.md`
- لوحة الفريج: `02_ALFORAIJBOARD_DASHBOARD/README.md`
- هيرمس: `03_HERMES_OPS/README.md`

## الخطوة المطلوبة لإصلاح Netlify نهائيًا

انشر من:

`D:\foraj_social\287\vs\site`

ويجب توفير:

- `NETLIFY_AUTH_TOKEN`
- `NETLIFY_SITE_ID`

خزّن القيم كمتغيرات بيئة أو GitHub Secrets فقط، ولا تضعها داخل markdown.
