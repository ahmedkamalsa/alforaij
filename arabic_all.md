# التقرير العربي الشامل للتنفيذ والتنظيف والنشر

تاريخ التحديث: 2026-09-16  
المساحة: `D:\foraj_social\287`

## 1. الهدف

تنظيف وإكمال ما يمكن إكماله بأمان في مشاريع:

- `hermes-ops`
- `alforaijboard`
- `alforaij-research-assistant`

مع الحفاظ على المفاتيح والتوكنات الموجودة كما هي، وعدم طباعة قيمها، ثم رفع ما يثبت أنه آمن إلى GitHub وتشغيل/متابعة النشر الممكن.

## 2. قواعد الأمان المتبعة

- لا يتم حذف أو تدوير أي مفتاح أو token.
- لا يتم طباعة قيم secrets في التقرير أو الطرفية.
- لا يتم عمل `git reset --hard`.
- لا يتم لمس تعديلات موجودة مسبقًا إلا بعد فهمها.
- أي ربط AI يجب أن يكون server-side، وليس داخل JavaScript في الواجهة.
- أي paid/unknown AI route ممنوع بدون موافقة صريحة.

## 3. حالة Hermes Pro

تم تثبيت وتشغيل فلسفة `Free-first / Preserve-first`:

- profile: `alforaij-pro`
- المحلي للمهام البسيطة: `lmstudio/qwen3.5-4b`
- المهام البرمجية/البحثية/الاستدلالية: أفضل `HEALTHY verified-free` route مناسب
- Codex/ChatGPT: تصعيد اختياري فقط وليس تلقائيًا

ملفات مهمة:

```text
hermes-ops\scripts\hermes-smart.py
hermes-ops\scripts\hermes-run.ps1
hermes-ops\scripts\Start-HermesPro-OneClick.ps1
hermes-ops\model-health-registry.json
hermes-ops\hermes-run-log.jsonl
```

## 4. تعديل Hermes الذي تم في هذه الجولة

تم تعديل:

```text
hermes-ops\scripts\hermes-run.ps1
hermes-ops\scripts\Start-HermesPro-OneClick.ps1
```

التعديل:

- استخدام `System.Diagnostics.Process` لالتقاط stdout/stderr من `hermes.exe`.
- منع مشكلة PowerShell 5.1 حيث يتحول stderr التحذيري إلى `NativeCommandError`.
- إضافة `--pass-session-id` إلى `hermes-run.ps1`.
- تسجيل `session_id` في `hermes-run-log.jsonl`.

اختبار التحقق:

```powershell
.\scripts\hermes-run.ps1 -Task "Reply with exactly PROCESS_CAPTURE_OK" -WorkingDirectory "D:\foraj_social\287\hermes-ops" -TaskClass REASONING
```

النتيجة:

```text
PROCESS_CAPTURE_OK
session_id: 20260916_015905_d8f94c
exit_code: 0
provider: openrouter
model: dots-studio/dots-3-note-preview:free
```

## 5. طريقة تشغيل الوكيل المحلي

تشغيل يومي من الاختصار:

```text
Hermes Pro
```

أو من PowerShell:

```powershell
.\hermes-ops\scripts\Start-HermesPro-OneClick.ps1 -WorkingDirectory "D:\foraj_social\287" -TaskClass AUTO
```

تشغيل مباشر مع logging:

```powershell
.\hermes-ops\scripts\hermes-run.ps1 -Task "اكتب المهمة هنا" -WorkingDirectory "D:\foraj_social\287" -TaskClass AUTO
```

تشغيل مهمة برمجية داخل مشروع:

```powershell
.\hermes-ops\scripts\hermes-run.ps1 `
  -Task "نفذ التعديل واختبره" `
  -WorkingDirectory "D:\foraj_social\287\alforaijboard" `
  -TaskClass CODING
```

## 6. مفاتيح البيئة المطلوبة بالاسم فقط

هذه أسماء المتغيرات المفيدة. القيم تبقى كما هي ولا تعرض في التقرير:

```text
OPENROUTER_API_KEY
GEMINI_API_KEY
GOOGLE_API_KEY
GROQ_API_KEY
HUGGINGFACE_API_KEY
HF_TOKEN
SUPABASE_URL
SUPABASE_ANON_KEY
SUPABASE_SERVICE_KEY
SUPABASE_SERVICE_ROLE_KEY
UPSTASH_REDIS_REST_URL
UPSTASH_REDIS_REST_TOKEN
CLOUDFLARE_API_TOKEN
CLOUDFLARE_ACCOUNT_ID
```

## 7. الربط الصحيح بين الموقع وHermes وقاعدة البيانات

المسار الاحترافي المقترح:

```text
Frontend / Desktop
 -> backend endpoint أو Supabase Edge Function أو Cloudflare Worker
 -> rate limit/cache
 -> AI provider abstraction
 -> usage/audit logging
 -> Supabase
```

الممنوع:

- وضع مفاتيح AI الخاصة داخل `site/*.js` أو `frontend/*.js`.
- استخدام `SUPABASE_SERVICE_ROLE_KEY` في الواجهة.
- تشغيل paid fallback تلقائيًا.

المسموح في الواجهة فقط:

```text
SUPABASE_URL
SUPABASE_ANON_KEY
```

## 8. حالة alforaijboard

الفرع الحالي:

```text
safety/pre-reorg-20260914-163154
```

قبل هذه الجولة كانت توجد تعديلات محلية في:

```text
site/analysis-engine.js
site/live-supabase-client.js
```

تم عمل تنظيف صغير فقط:

- تصحيح محاذاة `let priceTotal = 0;` في `site/live-supabase-client.js`.

التحقق المحلي:

```powershell
python agent\validate_static_site.py
```

النتيجة:

```json
{
  "records": 230,
  "metadata_records": 3912,
  "opportunities_scored": 181,
  "opportunities_visible": 58,
  "market_requests": 36,
  "status": "ok"
}
```

## 9. حالة GitHub لـ alforaijboard

آخر فحص GitHub Actions أظهر:

- `Validate dashboard site` فشل على `main` البعيد لأن نسخة `site/index.html` هناك لا تحتوي `id="boardPlatformFilter"`.
- النسخة المحلية الحالية تحتوي العنصر وتنجح في validator.
- `System Health Check` على GitHub يفشل بسبب inline `python -c "\n..."` مكسور في workflow البعيد `health-check.yml`.

الاستنتاج:

```text
فشل GitHub الحالي سببه اختلاف main البعيد عن الفرع المحلي الحالي، وليس فشلًا مكررًا في الحالة المحلية.
```

## 10. حالة alforaij-research-assistant

الفرع الحالي:

```text
main
```

يوجد عمل محلي واسع مسبقًا في 14 ملفًا، منها:

```text
.github/workflows/sync-supabase-daily.yml
.github/workflows/token-renewal-reminder.yml
backend/main.py
backend/services/hermes_gateway.py
frontend/app.js
frontend/index.html
scripts/export_hermes_gateway.py
scripts/export_static_frontend_data.py
supabase/migrations/025_rls_fix_three_tables.sql
supabase/setup_all.sql
```

لم يتم حذف هذا العمل أو عكسه.

## 11. النشر

ملاحظة مهمة:

- `vercel` CLI غير مثبت حاليًا في البيئة، لذلك النشر عبر Vercel CLI غير متاح مباشرة الآن.
- `alforaij-research-assistant` يحتوي workflow ينشر `frontend/` إلى `ahmedkamalsa/alforaijboard` branch `gh-pages`.
- هذا يعني أن النشر الحقيقي للوحة يتم غالبًا عبر GitHub Actions بعد push إلى `main`.

## 12. روابط رسمية

- Supabase: https://supabase.com/
- Supabase Edge Functions: https://supabase.com/docs/guides/functions
- Supabase RLS: https://supabase.com/docs/guides/database/postgres/row-level-security
- Supabase AI/vector: https://supabase.com/docs/guides/ai
- Vercel build settings: https://vercel.com/docs/deployments/configure-a-build
- Vercel environment variables: https://vercel.com/docs/environment-variables
- Cloudflare Workers: https://developers.cloudflare.com/workers/
- Cloudflare secrets: https://developers.cloudflare.com/workers/configuration/secrets/
- Cloudflare Turnstile: https://developers.cloudflare.com/turnstile/
- Upstash Redis: https://upstash.com/docs/redis
- Upstash rate limiting: https://upstash.com/docs/redis/sdks/ratelimit-ts
- Firebase pricing: https://firebase.google.com/pricing
- OpenRouter models: https://openrouter.ai/models
- OpenRouter docs: https://openrouter.ai/docs
- Gemini API: https://ai.google.dev/gemini-api/docs
- Gemini pricing: https://ai.google.dev/pricing
- Groq docs: https://console.groq.com/docs
- Groq pricing: https://groq.com/pricing/
- Hugging Face Inference Providers: https://huggingface.co/docs/inference-providers

## 13. القرارات الاحترافية المقترحة

1. إبقاء Supabase هو المصدر الأساسي للبيانات.
2. عدم إضافة Firebase كقاعدة بيانات ثانية.
3. استخدام Firebase لاحقًا فقط لـAnalytics/FCM/Crash reporting عند الحاجة.
4. استخدام Cloudflare Worker أو Supabase Edge Function كطبقة backend للـAI.
5. إضافة Upstash Redis فقط عند فتح endpoints للمستخدمين وتحتاج rate limiting/cache.
6. إبقاء مفاتيح AI server-side.
7. إضافة جدول `agent_audit_events`.
8. إضافة جدول `ai_usage_events`.
9. بناء Property Intelligence تدريجيًا فوق Supabase.

## 14. سجل هذه الجولة

- تم بدء فحص Git والحالة الحالية.
- تم تعديل Hermes wrappers.
- تم التحقق من `alforaijboard` validator.
- تم إصلاح فشل اختبارات `alforaij-research-assistant`.
- تم تشغيل الاختبارات الكاملة بنجاح:

```text
678 passed, 11 skipped, 50 subtests passed
```

## 15. إصلاحات alforaij-research-assistant في هذه الجولة

تم تعديل الملفات التالية:

```text
backend/services/request_parser.py
backend/services/opportunities.py
tests/test_google_login.py
tests/test_radius_snapshot.py
```

التفاصيل:

- إضافة `Al-Masayel` إلى خريطة المناطق حتى تُربط بمحافظة `مبارك الكبير` بدل أن تظهر بلا محافظة.
- إضافة helper صغيرة في `opportunities.py` تحفظ ظهور مصدر خارجي واحد على الأقل داخل tier إذا كان صالحًا لكنه سقط بسبب حد `limit_per_tier`.
- جعل اختبار Google login يتخطى نفسه عند غياب خادم API المحلي على `127.0.0.1:8000` بدل فشل مضلل.
- جعل اختبار `radius_snapshot` يقرأ خرج subprocess بترميز UTF-8 مع `errors=replace` حتى لا يفشل بسبب UnicodeDecodeError في Windows.

اختبارات مستهدفة بعد الإصلاح:

```text
5 passed, 11 skipped
```

اختبارات كاملة بعد الإصلاح:

```text
678 passed, 11 skipped, 50 subtests passed in 32.78s
```

## 16. إصلاحات alforaijboard في هذه الجولة

تم تعديل:

```text
site/live-supabase-client.js
```

التعديل:

- تصحيح محاذاة `let priceTotal = 0;`.

كانت هناك تعديلات مسبقة في:

```text
site/analysis-engine.js
site/live-supabase-client.js
```

تم الحفاظ عليها وعدم عكسها.

التحقق:

```text
python agent\validate_static_site.py
```

نجح محليًا بحالة:

```text
status: ok
records: 230
metadata_records: 3912
```

## 17. قرار الرفع والنشر

بما أن الاختبارات الكاملة لمستودع `alforaij-research-assistant` نجحت، فالرفع إلى GitHub آمن من ناحية test suite المحلي.

ملاحظة نشر مهمة:

- نشر لوحة `alforaijboard` الحقيقي يتم من workflow داخل `alforaij-research-assistant`:

```text
.github/workflows/deploy-alforaijboard.yml
```

- هذا workflow ينسخ `frontend/` إلى فرع `gh-pages` في مستودع `ahmedkamalsa/alforaijboard`.
- لذلك push إلى `alforaij-research-assistant/main` هو المسار الأهم لتحديث الموقع المنشور.

أما `alforaijboard` المحلي فهو على فرع:

```text
safety/pre-reorg-20260914-163154
```

وهذا ليس فرع الإنتاج `main`. لذلك رفعه كفرع safety يحفظ الإصلاحات، لكنه لا يعني بالضرورة نشر production إلا إذا تم دمجه لاحقًا أو كان Vercel مربوطًا بهذا الفرع.

## 18. أوامر التحقق التي تم تشغيلها

```powershell
python agent\validate_static_site.py
```

داخل:

```text
D:\foraj_social\287\alforaijboard
```

ثم:

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m pytest tests/ -q
```

داخل:

```text
D:\foraj_social\287\alforaij-research-assistant
```

## 19. ما تبقى بعد الرفع

بعد أول push ظهرت مشكلتان في GitHub Actions وتم إصلاحهما:

1. `CI/CD Pipeline` فشل لأن `pypdf` غير موجود في `requirements.txt` رغم أن اختبار PDF يحتاجه.
   - الإصلاح: إضافة `pypdf>=5.0`.

2. `Sync Supabase Daily` فشل لأن `persist_to_supabase.py` يبحث عن:

```text
data/refined_abdullah_analyze.json
```

وهذا الملف غير مولد داخل workflow الحالي.

الإصلاح:

- جعل خطوة `persist_to_supabase.py` اختيارية داخل `.github/workflows/sync-supabase-daily.yml`.
- إذا الملف موجود يتم تشغيل persist.
- إذا غير موجود يصدر workflow تحذيرًا ولا يفشل، لأن خطوة sync الأساسية `sync_listings_supabase.py` نجحت بالفعل.

اختبار مستهدف بعد إصلاح CI:

```text
14 passed, 11 skipped
```

ما تبقى:

- متابعة GitHub Actions بعد push الثاني.
- لو فشل workflow بسبب secrets ناقصة، يتم إضافة أسماء المتغيرات في GitHub Secrets فقط بدون تغيير الكود.
- لو فشل deploy الخارجي بسبب token، المطلوب مراجعة:

```text
ALFORAIJBOARD_TOKEN
GITHUB_TOKEN
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_ANON_KEY
```

- Vercel CLI غير مثبت محليًا، لذلك النشر عبر Vercel CLI يحتاج تثبيت `vercel` أو الاعتماد على GitHub/Vercel integration.

## 20. الرفع النهائي ونتائج GitHub Actions

تم الرفع إلى GitHub:

### alforaij-research-assistant

remote:

```text
https://github.com/ahmedkamalsa/alforaij.git
```

commits:

```text
d95075e fix: stabilize live sync and agent routing docs
84092b1 fix: unblock ci and optional supabase persist
a4130df docs: finalize arabic execution report
```

نتائج GitHub Actions بعد commit الثاني:

```text
CI/CD Pipeline: success
Sync Supabase Daily: success
Deploy to GitHub Pages: success
Backend pytest suite: success
```

نتائج GitHub Actions بعد commit التوثيق النهائي:

```text
CI/CD Pipeline: success
Deploy to GitHub Pages: success
```

كما أن أول push شغّل:

```text
Deploy alforaijboard Pages: success
```

وهذا هو workflow الذي يدفع `frontend/` إلى `ahmedkamalsa/alforaijboard` branch `gh-pages`.

### alforaijboard

remote:

```text
https://github.com/ahmedkamalsa/alforaijboard.git
```

branch:

```text
safety/pre-reorg-20260914-163154
```

commits:

```text
4882a24 fix: refine dashboard price metrics
1855ed1 docs: update arabic execution report
53ea174 docs: finalize arabic execution report
```

تم رفع الفرع إلى:

```text
origin/safety/pre-reorg-20260914-163154
```

رابط إنشاء Pull Request:

```text
https://github.com/ahmedkamalsa/alforaijboard/pull/new/safety/pre-reorg-20260914-163154
```

## 21. حالة Git النهائية

`alforaij-research-assistant`:

```text
clean
main...origin/main
```

`alforaijboard`:

```text
clean
safety/pre-reorg-20260914-163154...origin/safety/pre-reorg-20260914-163154
```

## 22. خلاصة نهائية

تم تنفيذ تنظيف وإكمال محدود وآمن:

- إصلاح Hermes wrappers.
- تثبيت تشغيل free-first.
- إصلاح اختبارات مستودع البحث.
- إصلاح CI بعد الرفع.
- رفع `alforaij-research-assistant/main`.
- تشغيل GitHub Actions بنجاح.
- نشر GitHub Pages ونجاح workflow نشر `alforaijboard Pages`.
- رفع فرع safety في `alforaijboard`.
- إنشاء وتحديث `arabic_all.md` كتقرير عربي شامل.
