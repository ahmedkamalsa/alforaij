# إعداد Supabase

## المطلوب من لوحة Supabase

بعد إنشاء المشروع انسخ القيم التالية من:

`Project Settings -> API`

- `Project URL`
- `service_role key`

ثم ضعها في ملف `.env` محليًا:

```text
SUPABASE_URL=https://cuvakjwqrwkwwemjfefh.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
DATABASE_URL=
```

لا تضع `service_role key` في الواجهة أو GitHub Pages.
التطبيق يقرأ ملف `.env` تلقائيًا عند التشغيل المحلي.

## SQL المطلوب تشغيله

الأبسط: افتح SQL Editor وشغل الملف كاملًا:

```text
supabase/setup_all.sql
```

أو شغل الملفات بالترتيب:

1. `supabase/migrations/001_initial_schema.sql`
2. `supabase/migrations/002_source_quality_and_runs.sql`
3. `supabase/seed_source_registry.sql`
… إلخ (كل ملفات `supabase/migrations/` بالترتيب، منها:
   - `007_outreach_clicks.sql` لتتبع نقرات التسويق
   - `010_market_listings.sql` **لإعلانات السوق الخارجية المحصودة** — الوكيل اليومي يحفظ فيها كل إعلانات Mourjan/OpenSooq/Q8Aqar/… يوميًا (خطوة `persist_market_listings`) فتراكم قاعدة المعرفة مثل بيانات الفريج المحلية تمامًا
   - `011_official_indicators_sulaibikhat.sql` **لأسعار المتر الرسمية لصليبيخات** (600 د.ك/م² — مرجع 2025) حتى لا تبقى المنطقة بلا بيانات مرجعية في `official_market_indicators`)
   - `012_opportunities_total_listings.sql` **لعمود total_listings** في `opportunities` — يخزّن إجمالي الإعلانات المفحوصة منفصلًا عن الفرص المؤهلة حتى يعرض العدّاد «X فرصة من أصل Y إعلان» بدل X/X)

> ملاحظة: مؤشرات `official_market_indicators` **تُقرأ مباشرة من القاعدة** — إن لم يكن الترحيل `011` منشّذًا، تُعبَّأ الصفوف يدويًا أو عبر `_post` بنفس الحقول (region / reference_land_price_per_m2 / source_name / source_quarter / confidence / effective_from / effective_to / notes).

أو بعد وضع مفاتيح البيئة يمكن مزامنة سجل المصادر بالكود:

```powershell
python scripts\sync_source_registry_supabase.py
```

ولرفع إعلانات الفريج المحلية:

```powershell
python scripts\sync_listings_supabase.py
```

## التحديث اليومي

القاعدة ليست للفريج فقط. يوجد وكيل يومي باسم `daily_data_update_agent` يشغّل دورة كاملة ليبقى Supabase مستودعًا موحدًا:

```powershell
python scripts\daily_data_update.py
```

هذا يحدث:

- سجل المصادر.
- إعلانات الفريج في `listings`.
- الصفقات الرسمية في `official_transactions` إذا وفرت ملفًا أو رابطًا.
- لقطة الفرص اليومية في `opportunities`.
- مؤشرات الصحة والعدادات التي تظهر في `/api/health`.
- ملخص إشعارات مجاني في `/api/update-notifications`.
- حالة الوكيل في `/api/daily-agent/status`.

يمكن تشغيل الوكيل من المنصة نفسها من زر `تشغيل وكيل التحديث الآن` داخل ملخص التحديث اليومي، أو عبر API:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/daily-agent/run -Method Post -ContentType "application/json" -Body '{"includeExternal":true}'
```

لو وصلتك صفقات وزارة العدل كملف CSV/JSON:

```powershell
python scripts\daily_data_update.py --official-file data\moj_transactions.csv
```

أو كرابط داخلي يعيد CSV/JSON:

```powershell
python scripts\daily_data_update.py --official-url "https://example.com/moj_transactions.csv"
```

أو ضعها في `.env`:

```text
OFFICIAL_TRANSACTIONS_SOURCE=data\moj_transactions.csv
```

جدولة يومية على Windows Task Scheduler من PowerShell:

```powershell
$Action = New-ScheduledTaskAction -Execute "python" -Argument "scripts\daily_data_update.py" -WorkingDirectory "D:\foraj_social\287\alforaij-research-assistant"
$Trigger = New-ScheduledTaskTrigger -Daily -At 6:00am
Register-ScheduledTask -TaskName "AlforaijDailyDataUpdate" -Action $Action -Trigger $Trigger -Description "Update Alforaij unified real-estate data warehouse"
```

لا يتم إدخال الصفقات الرسمية في التقييم من صفحة غير منظمة أو رقم غير موثق. يجب أن تكون CSV/JSON فيها على الأقل: `reference, area, price, date`، ويفضل إضافة `property_type, transaction_type, space, original_url, source_note`.

لطباعة SQL كاملًا وتجهيزه للنسخ داخل SQL Editor:

```powershell
python scripts\print_supabase_sql.py
```

## وظيفة الجداول

- `listings`: كل إعلان من الفريج أو المصادر الخارجية بعد التنظيف.
- `saved_reports`: حفظ تقارير البحث والتقييم.
- `source_registry`: قائمة المنصات المعتمدة وحالتها وهل تدخل في التقييم.
- `source_runs`: سجل كل تشغيل لمصدر خارجي، وعدد النتائج التي وجدها وعدد ما دخل في التقييم.
- `listing_evidence`: دليل كل رقم داخل الإعلان مثل السعر أو المساحة أو رابط المصدر.
- `outreach_clicks`: تتبع نقرات التسويق (نسخ ملخص / إرسال واتساب لفرصة أو عميل) — تُجمَّع عدادات التفاعل لكل عميل في تبويب الأداء.

## سياسة الأمان

- الواجهة لا تتصل مباشرة بمفتاح `service_role`.
- أي كتابة في Supabase يجب أن تتم من backend فقط.
- المصادر الخارجية لا تدخل في تقييم السعر إلا إذا كان الإعلان نفسه يثبت المنطقة والنوع والعملية.
