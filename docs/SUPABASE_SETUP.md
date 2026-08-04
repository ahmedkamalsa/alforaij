# إعداد Supabase

## المطلوب من لوحة Supabase

بعد إنشاء المشروع انسخ القيم التالية من:

`Project Settings -> API`

- `Project URL`
- `service_role key`

ثم ضعها في ملف `.env` محليًا:

```text
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
DATABASE_URL=
```

لا تضع `service_role key` في الواجهة أو GitHub Pages.

## SQL المطلوب تشغيله

شغل الملفات بالترتيب من SQL Editor داخل Supabase:

1. `supabase/migrations/001_initial_schema.sql`
2. `supabase/migrations/002_source_quality_and_runs.sql`
3. `supabase/seed_source_registry.sql`

أو بعد وضع مفاتيح البيئة يمكن مزامنة سجل المصادر بالكود:

```powershell
python scripts\sync_source_registry_supabase.py
```

## وظيفة الجداول

- `listings`: كل إعلان من الفريج أو المصادر الخارجية بعد التنظيف.
- `saved_reports`: حفظ تقارير البحث والتقييم.
- `source_registry`: قائمة المنصات المعتمدة وحالتها وهل تدخل في التقييم.
- `source_runs`: سجل كل تشغيل لمصدر خارجي، وعدد النتائج التي وجدها وعدد ما دخل في التقييم.
- `listing_evidence`: دليل كل رقم داخل الإعلان مثل السعر أو المساحة أو رابط المصدر.

## سياسة الأمان

- الواجهة لا تتصل مباشرة بمفتاح `service_role`.
- أي كتابة في Supabase يجب أن تتم من backend فقط.
- المصادر الخارجية لا تدخل في تقييم السعر إلا إذا كان الإعلان نفسه يثبت المنطقة والنوع والعملية.
