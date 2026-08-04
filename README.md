# مساعد الفريج للبحث والتقييم العقاري

تطبيق محلي مستقل لتحليل الطلبات العقارية العربية، تحويلها إلى فلاتر، البحث داخل بيانات الفريج المحلية، وترتيب النتائج مع تقييم سعري استرشادي مبني على العروض المشابهة المتاحة.

هذا المشروع منفصل عن `alforaijboard` ولا يغير ملفات الموقع المنشور.

## التشغيل

```powershell
cd D:\foraj_social\287\alforaij-research-assistant
.\start-local.ps1
```

ثم افتح:

```text
http://127.0.0.1:8000
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
- OpenSooq وMourjan عند توفر إعلان حي يطابق المنطقة ونوع العقار ونوع العملية.
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

## MCP

يوجد خادم MCP أولي في `mcp_server/server.py`. يوفر نفس محرك التحليل بصيغة JSON، ومناسب كقاعدة ربط لاحقة مع Codex أو أدوات داخلية.
