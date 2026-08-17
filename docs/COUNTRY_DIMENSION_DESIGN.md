# وثيقة تصميم: بُعد الدولة في قاعدة البيانات (country_id / عملة / وحدات / مصادر)

> **وثيقة تصميم فقط — بلا تنفيذ.** تحدد كيف يُضاف بُعد الدولة إلى السكيما الحالية
> لتمهيد التوسع من الكويت إلى دبي ثم السعودية، دون المساس بسلوك الكويت الحالي.
> تستند إلى: `docs/EXPANSION_SA_UAE_REGISTERED_TRANSACTIONS.md` (مصادر الصفقات
> الموثقة) والسكيما الفعلية في `supabase/migrations/`.

## 1) المبدأ العام: بُعد سياق، لا نسخ منفصلة

المنصة اليوم «كويتية البندقية»: كل جدول يحمل `area`/`governorate` كسياق جغرافي
دون بُعد دولة. المبدأ المقترح: **إضافة `country_code` كعمود سياق عام لكل الجداول
ذات البيانات الجغرافية/السعرية** — تمامًا كما أُضيفت `governorate` بجانب `area`
دون نسخ الجداول. النتيجة: نفس الجداول، نفس دوال التقييم، مع فلترة دولة.

قرارات حاسمة مسبقًا:

- **لا جدول منفصل لكل دولة** — النسخ تُضاعف صيانة الموصلات والتقييم والواجهة،
  وتكسر «المقارنات عبر الدول» مستقبلًا.
- **`country_code` نص ISO قصير** (`KW`/`AE`/`SA`) لا `country_id` رقمي: أسهل
  قراءة، مستقر عبر النسخ الاحتياطي، ويطابق مفاتيح ملفات الإحداثيات. (الطلب ذكر
  `country_id` — القرار: كود ISO مع جدول مرجعي `countries` يمنح الباقي.)
- **الافتراضي `KW`** في كل العمود الجديدة: صفر تغيير سلوكي على الكويت الحالية
  (الصفوف القديمة تبقى `KW` بدون backfill عنيف — أو backfill صريح بالترحيل).

## 2) جدول مرجعي `countries`

```sql
create table if not exists public.countries (
  code text primary key,                 -- 'KW' | 'AE' | 'SA' …
  name_ar text not null,                 -- 'الكويت' | 'الإمارات (دبي)' | 'السعودية'
  name_en text not null,
  currency_code text not null,           -- 'KWD' | 'AED' | 'SAR'
  currency_symbol text not null,         -- 'د.ك' | 'د.إ' | 'ر.س'
  rate_to_kwd numeric not null default 1,-- سعر صرف مرجعي للعرض الموحّد فقط (لا للحساب)
  area_unit text not null default 'م²',  -- مقياس المساحة (دبي بياناتها مترية: sq.m)
  price_precision integer not null default 0, -- أرقام عشرية للعرض
  locale text not null default 'ar',     -- تقويم/أرقام الواجهة
  default_governorate_label text not null default 'المحافظة',
  created_at timestamptz not null default now()
);
-- التهيئة: KW (d.ك، 1.0)، AE (د.إ، ~0.082)، SA (ر.س، ~0.081) — القيم الاسترشادية
-- تُحدَّث في الترحيل الفعلي من مصدر صرف موثق، وتُستخدم للعرض التوضيحي فقط.
```

**قاعدة صارمة:** التحويل النقدي للعرض التوضيحي فقط (`rate_to_kwd`) — الحسابات
(وسيط، فجوة السعر، العائد) تُجرى دائمًا بعملة الدولة الأصلية. لا يُخلط
`KWD + AED` في أي وسيط أبدًا.

## 3) إضافات الأعمدة لكل جدول (مرجع كامل)

| الجدول | عمود جديد | الافتراضي | لماذا |
|---|---|---|---|
| `market_listings` | `country_code` + `currency_code` | `'KW'` / `'KWD'` | سياق كل إعلان محصود؛ العملة تسمح بحفظ السعر الأصلي |
| `official_transactions` | `country_code` + `currency_code` + `city` | `'KW'` / `'KWD'` | الصفقات المسجلة لكل دولة؛ `city` لأن السعودية 13 منطقة ← 175 مدينة ← حي |
| `listing_price_observations` | `country_code` | `'KW'` | الخط الزمني يتبع الدولة (منسوب عبر `market_listings`) |
| `price_trends` | `country_code` | `'KW'` | **يدخل في المفتاح المركّب**: `unique (country_code, area, property_type, month, transaction)` |
| `source_registry` | `country_code` | `'KW'` | كل مصدر ينتمي لدولة (الحسبة/4Sale ← KW؛ DLD ← AE؛ وزارة العدل ← SA) |
| `source_runs` | `country_code` | `'KW'` | سجل التشغيل لكل دولة |
| `users` | `country_code` | `'KW'` | نطاق الحساب والتنبيهات (رقم +965 ← KW، +966 ← SA…) |
| `saved_searches` | `country_code` | `'KW'` | البحث المحفوظ يخص دولة |
| `user_alerts` | `country_code` | `'KW'` | التنبيهات تتبع دولة البحث |
| `portfolios` | `country_code` | `'KW'` | عقار المحفظة في دولته |
| `share_counts` | `opportunity_code` يحملها | — | لا حاجة (الفرصة نفسها تحمل الدولة) |
| `demand_indicators` (مُحسَبة) | `country_code` | `'KW'` | مؤشرات الطلب تُبنى لكل دولة |

**قيد تحقق موحّد** (نمط يُطبَّق في الترحيل):
```sql
alter table market_listings
  add constraint market_listings_country_currency_chk
  check (currency_code = (select currency_code from countries where code = country_code));
```
(تنفيذًا عمليًا: إما `currency_code` يُستنتج من `country_code` عبر VIEW، أو يُملأ
من الجدول المرجعي عند الكتابة — تُرجأ التفاصيل لخطة التنفيذ.)

## 4) السياسات الأساسية

### 4.1 العملة والسعر
- **احفظ دائمًا السعر بعملة الدولة الأصلية** (`price` + `currency_code`).
- العرض: `formatMoney` يستقبل `currency_symbol` من سياق الدولة المختارة.
- لا تحويل تلقائي في الحسابات — التحويل (`rate_to_kwd`) للعرض المقارن فقط.

### 4.2 الفهارس (تجنب مسح جدول كامل عبر الدول)
```sql
-- بديل الفهارس الحالية أحادية العمود أو إضافة مركبة:
create index … on market_listings (country_code, area);
create index … on official_transactions (country_code, area, date desc);
create index … on price_trends (country_code, month desc);
```

### 4.3 الواجهة والجغرافيا
- مبدّل الدولة في الشريط العلوي يضبط: نطاق البحث، العملة، ملف الإحداثيات، وقوائم المناطق.
- الجغرافيا: ملف إحداثيات لكل دولة (نمط `data/kuwait_areas.json`):
  - `data/kuwait-areas.json` (موجود — 139 نقطة)
  - `data/dubai-areas.json` (قائمة DLD الرسمية `dld_lkp_areas` — ~300 منطقة مسجلة)
  - `data/saudi-areas.json` (13 منطقة ← 175 مدينة ← 13,398 حيًا — الأحياء مرحلة لاحقة)
- المفاتيح تُطبَّع بنفس `normalizeArabic` لكل دولة.

### 4.4 التقييم (الوسيط الأثقل)
- دالة الوسيط في `valuation.py` تُقيَّد بمعامل الدولة: `get_official_transaction_rate(country='KW', area=…)`.
- تطبيع أسماء المناطق لكل دولة (خريطة الـ33 صيغة السعودية مرجع في `region_mapping.csv` بالمستودع المستقل الموثق).
- `official_transactions` يبقى المصدر الأعلى وزنًا — الآن بفلتر دولة.

## 5) مصادر كل دولة (مرجع)

| الدولة | صفقات مسجلة (أساس التقييم) | مؤشرات/إيجار | إعلانات (موصلات) |
|---|---|---|---|
| الكويت | الحسبة — `official_transactions` (قائم) | مؤشرات رسمية OFFIND | 4Sale/OpenSooq/Mourjan/Q8Aqar (قائم) |
| دبي | **DLD Open Data + Dubai Pulse** (CSV/API مجاني، ~1.5M صفقة 2004–) | مؤشر DLD السكني + Rental Index API (مدفوع 30K د.إ/سنة — اختياري) | PropertyFinder/Bayut/Dubizzle (مرحلة موصلات) |
| السعودية | **وزارة العدل** (CSV ربع سنوي مجاني، 1.4M صفقة 2020–2025، بلا نوع عقار في معظم السنوات) | **REGA** (مؤشرات بيع 6/13 منطقة + إيجار 13 منطقة) + إيجار (10M عقد — مؤشرات فقط) | Aqar/عقار (مرحلة موصلات) |

التفاصيل الكاملة (الروابط، الوصول، الحقول، القيود القانونية) في
`docs/EXPANSION_SA_UAE_REGISTERED_TRANSACTIONS.md` — هذه الوثيقة تصميم السكيما،
وتلك مصدر البيانات.

## 6) ترتيب الترحيل المقترح (لخطة التنفيذ لاحقًا — بلا تنفيذ هنا)

1. **ترحيل السكيما** `024_country_dimension.sql`: جدول `countries` + أعمدة
   `country_code` لكل الجداول + الفهارس المركبة + قيود التحقق. كل التغييرات
   إضافية بافتراض `KW` — قابل للتراجع بـ `git revert`.
2. **الخلفية (backfill)**: `UPDATE … SET country_code='KW'` صريح (أو الاعتماد على
   الافتراضي) — يليه فحص عدّادات: عدد صفوف كل جدول بعد الدولة.
3. **الواجهة**: مبدّل الدولة + `formatMoney` بالسياق + ملفات الإحداثيات لكل دولة.
4. **استيراد دبي**: تعميم `import_official_transactions` على رؤوس CSV الإنجليزية
   (DLD) + تحويل الحقول (Transaction Number ← reference، Amount ← price…).
5. **استيراد السعودية**: نفس التعميم على رؤوس وزارة العدل + خريطة تطبيع المناطق.
6. **التقييم**: معامل الدولة في دوال الوسيط + اختبارات أن الكويت لم تتغير.

## 7) البوابات (معايير القبول عند التنفيذ)

- **الكويت لا تتغير**: كل الاختبارات الحالية (439) خضراء دون تعديل — الأعمدة
  الجديدة افتراضية `KW` وقراءات التقييم تُفلتر بالدولة الافتراضية.
- **لا خلط عملات**: اختبار وحدة يثبت أن وسيط `price_trends` لا يجمع KWD مع AED/SAR
  (المفتاح المركّب يشمل `country_code`).
- **صفر 404 في الكونسول**: مبدّل الدولة وأي نداء جديد محروس بنمط
  `shareCountsBase()` (درس فحص الجوال).
- **تراجع نظيف**: كل التغييرات إضافية (جداول/أعمدة/فهارس) — `git revert` بلا تعارض.
- **تحقق حي**: بعد الاستيراد التجريبي، فحص متصفح يثبت أن بطاقة تحليل كويتية تعرض
  بدينار كويتي وبطاقة دبي بدرهم إماراتي من نفس الشيفرة.
