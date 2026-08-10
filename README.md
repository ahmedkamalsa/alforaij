# مساعد الفريج للبحث والتقييم العقاري

تطبيق محلي مستقل لتحليل الطلبات العقارية العربية، تحويلها إلى فلاتر، البحث داخل بيانات الفريج المحلية، وترتيب النتائج مع تقييم سعري استرشادي مبني على العروض المشابهة المتاحة.

هذا المشروع منفصل عن `alforaijboard` ولا يغير ملفات الموقع المنشور.

## 📖 الدليل الشامل للمطوّرين والوكلاء

قبل أي تعديل أو إضافة، اقرأ **[docs/AGENT_CONTEXT.md](docs/AGENT_CONTEXT.md)** — المرجع الأول
الذي يشرح المشروع كاملًا من الكود الفعلي: المعمارية، كل نقاط API، آلية جلب كل مصدر،
جداول قاعدة البيانات، الواجهة والتبويبات، الوكيل اليومي، مبادئ التقييم، الاختبارات،
والنشر. أي وكيل أو مطوّر جديد يبدأ منه بدل إعادة اكتشاف المشروع.

## التشغيل

```powershell
cd D:\foraj_social\287\alforaij-research-assistant
.\start-local.ps1
```

أو مباشرة (نقطة الدخول هي `backend/main.py` — لا يوجد `main.py` على المستوى الأعلى):

```bash
cd alforaij-research-assistant
PYTHONIOENCODING=utf-8 python -m backend.main
```

> `PYTHONIOENCODING=utf-8` ضروري على Windows لتجنب مشاكل ترميز النص العربي في المخرجات.

ثم افتح:

```text
http://127.0.0.1:8000
```

الافتراضيات: المضيف `127.0.0.1` والمنفذ `8000` (قابلان للتغيير عبر `ALFORAIJ_ASSISTANT_HOST` و`ALFORAIJ_ASSISTANT_PORT`). فحص الصحة: `curl http://127.0.0.1:8000/api/health`.

### التشغيل الخلفي مع سجل إلى ملف

```bash
cd alforaij-research-assistant
PYTHONIOENCODING=utf-8 nohup python -m backend.main > ../.freebuff/preview-thmsisewgqf6g6.log 2>&1 &
```

مسار السجل: `.freebuff/preview-thmsisewgqf6g6.log` نسبةً إلى جذر المشروع. تحقق من التشغيل بأمر منفصل: `netstat -ano | grep ':8000 ' | grep LISTENING`.

### مستوى السجل (متغير بيئة)

المتغير **`ALFORAIJ_LOG_LEVEL`** (يُقرأ في `backend/config.py`):

| القيمة | السلوك |
|---|---|
| `DEBUG` | كل التفاصيل: كل محاولة جلب لكل مصدر + نجاح كل جلب |
| `INFO` (الافتراضي) | سطر واحد لكل مصدر بعد كل تشغيل: الحالة + المدة + عدد المحاولات + النتائج + السبب |
| `WARNING` | الفشل فقط (ومسار إصلاح 4Sale عبر المصدر البديل) |
| `ERROR` | الأخطاء الحرجة فقط |

مثال: `ALFORAIJ_LOG_LEVEL=DEBUG PYTHONIOENCODING=utf-8 python -m backend.main`

### إيقاف الخادم

```bash
netstat -ano | grep ':8000 ' | grep LISTENING   # يظهر PID
taskkill //F //PID <PID>
```

## الاختبارات

```powershell
cd D:\foraj_social\287\alforaij-research-assistant
python -m unittest discover -s tests
```

## تحديث بيانات الفريج المحلية

```powershell
python scripts\import_board_payload.py --html ..\vs\site\index.html --out data\seed_listings.json
```

## ما يعتمد عليه التقييم الآن

- بيانات `data/seed_listings.json` المستخرجة من لوحة `alforaijboard`.
- OpenSooq وMourjan و**Yebtah** عند توفر إعلان حي يطابق المنطقة ونوع العقار ونوع العملية.
- تحليلات الحصاد لكل موقع (عدد الإعلانات/المناطق/وسيط السعر والمساحة) عبر `GET /api/market-analytics` وتظهر في تبويب «المصادر والتشغيل» من بيانات `market_listings` المتراكمة يوميًا.
- Q8Aqar يدخل فقط عندما يثبت رابط/نص الإعلان نفس الطلب، وإلا يظهر كمصدر مفحوص لا كمقارنة سعرية.
- Sakan حاليًا دليل توفر ورابط صفحة فقط، ولا يدخل في التقييم حتى يتوفر API أو endpoint تفاصيل قابل للتحقق.
- المقارنة تتم داخل نفس المنطقة ونفس نوع العقار قدر الإمكان.
- المساحة لا يتم استخراجها من كلمات مثل `ارتداد` أو `واجهة` أو `عرض الشارع`.
- التقييم استرشادي وليس تقييمًا رسميًا.

## Supabase

ملفات السكيما موجودة في `supabase/migrations`. اتبع [docs/SUPABASE_SETUP.md](docs/SUPABASE_SETUP.md) ثم ضع `SUPABASE_URL` و`SUPABASE_SERVICE_ROLE_KEY` في `.env` عند بدء الربط الفعلي.

بعد ضبط المفاتيح:

```powershell
python scripts\sync_source_registry_supabase.py
python scripts\sync_listings_supabase.py
```

كل تحليل جديد سيحاول حفظ التقرير وسجل تشغيل المصادر تلقائيًا. إذا لم توجد المفاتيح سيعمل التطبيق محليًا ويعرض `Supabase: غير مضبوط`.

## توليد تقرير PDF بعد البحث

أمر واحد يعيد البحث الكامل ويولّد التقريرين في `reports/` (يحدّثهما بعد كل بحث):

```powershell
python scripts\generate_office_pdf.py "يبي ايجار مكتب بالعاصمة او حولي شي رخيص بحدود ٢٠٠"
```

- `reports\office-rent-hawally-capital.pdf` — النسخة الأساسية.
- `reports\تقرير-مكاتب-حولي-العاصمة.pdf` — عنوان عربي + جدول النتائج والتقييم + جدول «المصادر والأدلة» + صفحة توصيات العميل.
- بدون وسيط نصي يُستخدم البحث الافتراضي (مكاتب إيجار حولي/العاصمة بحدود ٢٠٠ د.ك).

## MCP

يوجد خادم MCP أولي في `mcp_server/server.py`. يوفر نفس محرك التحليل بصيغة JSON، ومناسب كقاعدة ربط لاحقة مع Codex أو أدوات داخلية.

## استكشاف الأخطاء الشائعة

- **`can't open file '...\main.py'`** — شغّلت `main.py` من مكان خاطئ؛ استخدم `python -m backend.main` من داخل `alforaij-research-assistant`.
- **المنفذ 8000 مشغول** — يوجد خادم قديم يعمل؛ أوقفه (قسم «إيقاف الخادم») ثم أعد التشغيل.
- **4Sale دائمًا `failed` بخطأ DNS** — يعود غالبًا للشبكة/الحظر؛ الآلية الحالية تعيد المحاولة (حتى 4) ثم تلجأ لمصدر بديل (OpenSooq) مع إفصاح شفاف في التقرير، والسجل يعرض `مصدر 4Sale → fallback | …ms | محاولات 4 | نتائج N | …`.
- **السجل لا يعرض تفاصيل المحاولات** — المستوى `INFO` يُخفي تفاصيل `fetch_url` (DEBUG)؛ اضبط `ALFORAIJ_LOG_LEVEL=DEBUG` عند التشخيص.
