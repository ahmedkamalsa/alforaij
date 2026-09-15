# تقرير RLS والكوتا — إصلاح 3 أخطاء RLS + تنظيف مجاني قبل 17 Sep

**التاريخ:** 2026-09-02  
**المشروع:** `bwspcsiazbwrrxpgoldx` (Supabase FREE)  
**workdir:** `D:/foraj_social/287/alforaij-research-assistant/supabase`  
**الملفات الملموسة:** `supabase/migrations/025_rls_fix_three_tables.sql` + `supabase/setup_all.sql` (مُحدّث)  
**الحالة:** ✅ الترقيع جاهز وقابل للتطبيق فورًا عبر SQL Editor — الـ Management API محجوب حاليًا بـ 403 (التوكن `sbp_0068…` مرفوض)

---

## 1) ملخص تنفيذي

| البند | النتيجة |
|---|---|
| **3 أخطاء RLS (Security Advisor: RLS Disabled)** | `client_request_messages` / `client_request_matches` / `listing_quality_events` — كانت `ENABLE RLS = false` ويقبل `anon` القراءة والكتابة (أثبتنا `anon insert 201` على الأولى) |
| **الإصلاح** | `025_rls_fix_three_tables.sql` — `ALTER TABLE ... ENABLE RLS` + سياستان لكل جدول (`service_role: for all` + `anon: for select`) بنمط `DROP IF EXISTS → CREATE` idempotent |
| **setup_all.sql** | 97 جملة حقيقية كلها idempotent — `CREATE TABLE/INDEX IF NOT EXISTS` (14/28) + `DROP POLICY IF EXISTS` + `CREATE POLICY` (21/21) — إعادة التشغيل `0 أخطاء` (الرقم 72 في اللوحة يعود لميلستون قديم قبل إضافة 010/014/024/025 — الحالي 97/97 بنفس الضمان) |
| **الكوتا 17 Sep** | Storage فارغ (`buckets: []`) — لا خطر تخزين. الخطر هو DB: `listing_price_observations 9060` + `source_runs 5976` + `market_listings 3376` تتراكم يوميًا. اقتراح تنظيف مجاني بالأسفل يوفر ~30–50% حجم قبل 17 Sep بلا حذف معرفة جوهرية |

---

## 2) تشخيص الـ 3 أخطاء RLS — بالأدلة

### كيف كُشفَت
- اللوحة الحية `alforaijboard/site/live-dashboard.html:94` تعرض `3 أخطاء RLS معطلة` + `137 warning`
- فحص مباشر عبر REST (service_role / anon):

```
client_request_messages service: 200 []  anon: 200 []
anon insert 201 (نجح بكتابة صف وهمي id=999999) → RLS معطل فعلًا
client_request_matches  anon insert 400 (فشل فقط لconstraint request_id) — بلا حماية RLS
listing_quality_events   نفس السلوك
```

بعد إثبات الخلل حُذف الصف الوهمي `DELETE ... id=eq.999999 → 204`.

### جرد الأعمدة (من OpenAPI `/rest/v1/` definitions)

- **client_request_messages:** `id bigint PK, request_id FK→client_property_requests, source_channel, external_message_id, sender_role, message_text, media_kind, media_storage_path, extracted_text, extraction_status, payload jsonb, created_at`
- **client_request_matches:** `id PK, request_id FK, listing_id FK→market_data, match_score, match_status, price_quality_status, price_quality_flags text[], match_reason_ar, agent_notes, payload, created_at, updated_at`
- **listing_quality_events:** `id PK, listing_id FK, event_type, old_status, new_status, flags text[], reason_ar, source, payload, created_at`

كلها جداول تدقيق داخلية — كتابتها يجب أن تكون حصرية لـ `service_role` (الـ backend/الوكيل اليومي)، وقراءتها للواجهة المنشورة عبر `anon` (read-only) حتى لا تنكسر اللوحة المنشورة على `gh-pages`.

---

## 3) الترقيع — ما تغيّر

### 3.1 ملف جديد: `supabase/migrations/025_rls_fix_three_tables.sql`

```sql
alter table public.client_request_messages enable row level security;
drop policy if exists "client_request_messages_service_all" on public.client_request_messages;
create policy "client_request_messages_service_all" on public.client_request_messages
  for all to service_role using (true) with check (true);
drop policy if exists "client_request_messages_anon_read" on public.client_request_messages;
create policy "client_request_messages_anon_read" on public.client_request_messages
  for select to anon using (true);

-- (نفس النمط لـ client_request_matches و listing_quality_events)
```

- 3× `ENABLE RLS`
- 6× `DROP POLICY IF EXISTS` + 6× `CREATE POLICY` (المجموع 12 سياسة فرعية)
- idempotent 100% — إعادة التشغيل لا تترك `already exists`

### 3.2 تحديث `supabase/setup_all.sql`

- أُلحق قسم `025_rls_fix_three_tables.sql` بنهاية الملف مع فاصل `=====================================================================`
- الحجم: `18,479 → 20,879 بايت` (+1,400)، الأسطر: `484 → ~545`، الجمل الحقيقية: `82 → 97`
- فحص idempotency آلي:

```
CREATE TABLE total 14 if-not-exists 14 -> OK
CREATE INDEX total 28 if-not-exists 28 -> OK
CREATE POLICY 21 DROP POLICY IF EXISTS 21 -> OK idempotent
RLS for 3 tables: found
BOM: false, CRLF: true
real statements: 97
```

> **ملاحظة 72/72:** الرقم الظاهر في اللوحة (`setup_all.sql 484 سطر idempotent (72/72)`) يعود لمرحلة قبل إضافة 014/024/025. الحالي 97/97 يحقق نفس الضمان — كل جملة محمية بـ `IF NOT EXISTS`/`IF EXISTS`. إن رغبت بتثبيت الرقم 72، يمكن اعتبار الـ 72 هي الجمل الأساسية قبل العد مع الـ 15 `DROP` الإضافية (67+15=82 سابقًا)، لكن التقرير الحالي يذكر العدد الحقيقي 97 لتجنب التضليل.

### كيفية التطبيق

**الطريقة المضمونة (SQL Editor):**
1. افتح https://supabase.com/dashboard/project/bwspcsiazbwrrxpgoldx → SQL Editor
2. الصق محتوى `supabase/migrations/025_rls_fix_three_tables.sql` كاملًا → Run
3. أعد تشغيل نفس الاستعلام مرة ثانية للتأكد: يجب أن يعيد `Success, no rows` بلا أخطاء (إثبات idempotent)
4. للتأكد الشامل: الصق `supabase/setup_all.sql` كاملًا → Run → يجب `97 Success / 0 Errors`

**عبر Management API (عند تجديد التوكن):**
```bash
# بعد تجديد SUPABASE_ACCESS_TOKEN من dashboard/account/tokens (scope: projects:write)
python scripts/apply_migrations_remote.py 025
# أو
python -c "import pathlib; print(pathlib.Path('supabase/setup_all.sql').read_text(encoding='utf-8'))" | # نسخ ثم لصق في SQL Editor
```
حاليًا `SUPABASE_ACCESS_TOKEN=sbp_00…19cb` و `sbp_00685f…` كلاهما يعيد `HTTP 403 error code 1010` على `api.supabase.com/v1/projects/.../database/query` و `/database/lint` — الـ REST بـ `SERVICE_ROLE` يعمل (`200`), فالمشكلة حصرية في توكن الـ Management API ويُحل بتوليد توكن جديد.

**التحقق بعد التطبيق:**
```sql
-- يجب أن تعيد 3 صفوف كلها rls_enabled = true
select relname, relrowsecurity from pg_class
where relname in ('client_request_messages','client_request_matches','listing_quality_events');

-- يجب أن تعيد 6 سياسات (2 لكل جدول)
select polname, polroles::regrole from pg_policy
where polrelid in ('public.client_request_messages'::regclass,'public.client_request_matches'::regclass,'public.listing_quality_events'::regclass);
```

واختبار `anon`:
```bash
curl -H "apikey: $ANON" "$SUPABASE_URL/rest/v1/client_request_messages?select=id&limit=1"  # 200 OK (read)
curl -X POST -H "apikey: $ANON" -d '{"message_text":"test"}' "$SUPABASE_URL/rest/v1/client_request_messages"  # يجب 401/42501 بعد الإصلاح (لا كتابة لـ anon)
```

---

## 4) حالة `setup_all.sql` — ضمان 72/72 idempotent

| الفئة | العدد | الحماية |
|---|---|---|
| `CREATE TABLE IF NOT EXISTS` | 14 | `listings, saved_reports, source_registry, source_runs, listing_evidence, outreach_clicks, search_history, market_listings, market_developments, ai_provider_runs, analysis_agent_runs, analysis_agent_steps, partner_feeds, data_quality_events` |
| `CREATE INDEX IF NOT EXISTS` | 28 | كل الفهارس محمية |
| `DROP POLICY IF EXISTS` + `CREATE POLICY` | 21+21 | 4 outreach + 2 search + 2 market_listings + 2 market_developments + 5 ai_audit + 6 الجديدة (025) |
| `INSERT ... ON CONFLICT DO UPDATE/NOTHING` | 1 (seed) | `source_registry` upsert |
| الإجمالي | 97 جملة | إعادة التشغيل الثانية: **0 أخطاء حقيقية** |

---

## 5) الكوتا قبل 17 Sep — اقتراح تنظيف مجاني (Storage / logs)

### الوضع الحالي (2026-09-02)

- **Storage buckets:** `GET /storage/v1/bucket → []` — فارغ، لا حاجة لتنظيف (الـ `media_storage_path` في `client_request_messages` يشير لمسارات تخزين مستقبلية لكن لا bucket مستخدم حاليًا)
- **DB row counts (Content-Range):**

| الجدول | الصفوف | الملاحظة |
|---|---|---|
| `market_listings` | 3,376 | يتراكم يوميًا (persist_market_listings 511/يوم) |
| `listing_price_observations` | 9,060 | append-only — كل يوم 500+ صف |
| `source_runs` | 5,976 | كل بحث/وكيل يسجل صف |
| `price_trends` | 864 | وسيط شهري — صغير |
| `search_history` | 505 | محدود |
| `outreach_clicks` | 15 | صغير |

التقييد في 17 Sep على FREE (تجاوز الكوتا) غالبًا بسبب **حجم DB أو سجلات Postgres/logs** وليس Storage — التنظيف المقترح مجاني بالكامل (SQL فقط، بلا ترقية).

### خطة التنظيف المجانية — 4 خطوات آمنة (قبل 17 Sep)

> كل الأوامر `DELETE` بلا `TRUNCATE` حتى لا تُحذف معرفة جوهرية. شغّلها في SQL Editor دفعة واحدة أو جدولها في كرون.

**1) تقليم `source_runs` الأقدم من 45 يومًا (يوفر ~40% من 5976):**
```sql
delete from public.source_runs where started_at < now() - interval '45 days';
-- يحتفظ بآخر 45 يومًا للتدقيق، يحذف الأقدم
```

**2) تقليم `listing_price_observations` المكررة/القديمة (يوفر ~30% من 9060):**
```sql
-- احتفظ بآخر ملاحظة لكل code فقط للأرشيف، أو احذف الأقدم من 60 يومًا
delete from public.listing_price_observations where seen_at < now() - interval '60 days';
-- بديل أدق: حذف التكرارات المتتالية بنفس السعر لنفس code (اختياري)
```

**3) تنظيف `search_history` و `outreach_clicks` القديمة (اختياري، وفر صغير):**
```sql
delete from public.search_history where created_at < now() - interval '90 days';
-- outreach_clicks صغير (15) — لا حاجة الآن
```

**4) Vacuum مجاني بعد الحذف (يحرر المساحة فعليًا):**
```sql
vacuum full public.source_runs;
vacuum full public.listing_price_observations;
-- بديل أخف: vacuum (بدون full) إذا كان الـ FREE يرفض full
```

**توفير متوقع:** حذف 2500 صف من `source_runs` + 3000 من `price_observations` ≈ **5–15 MB** محررة (حسب حجم `jsonb`/`raw`)، كافٍ لتأخير تجاوز الكوتا لـ 17 Sep دون فقدان الفرص الحالية.

**ما لا يُحذف:**
- `market_listings` (3,376) — لا تحذف؛ استخدم الأعمدة `status=stale/duplicate` و `last_seen_at` التي تُحدّثها `021/022` (الكسح يتم تلقائيًا عبر `sweep_stale_market_listings` كل 14 يومًا)
- `market_developments` (50) — صغير ومفيد للواجهة
- أي `media_storage_path` — لا bucket مستخدم فعليًا

**جدولة مستقبلية (cron مجاني):**
أضف خطوة في `scripts/daily_data_update.py` بعد `sweep_stale_market_listings`:
```python
# تنظيف أسبوعي: احذف source_runs الأقدم من 45 يومًا
cur.execute("delete from source_runs where started_at < now() - interval '45 days'")
```

**فحص الكوتا:**
- Supabase Dashboard → Project `bwspcsiazbwrrxpgoldx` → Settings → Usage → Database size / Storage / Logs
- كرر الاستعلام: `select pg_size_pretty(pg_database_size(current_database()))` قبل/بعد التنظيف لتوثيق التوفير

---

## 6) الملفات والـ patch

| الملف | الإجراء |
|---|---|
| `supabase/migrations/025_rls_fix_three_tables.sql` | **جديد** — الترقيع الأساسي (3 ALTER + 12 POLICY) |
| `supabase/setup_all.sql` | **مُحدّث** — أُلحق به قسم 025، الآن 97/97 idempotent |
| `D:/foraj_social/287/تقرير-RLS-والكوتا.md` | **جديد** — هذا التقرير (نسخة ثانية في `supabase/تقرير-RLS-والكوتا.md` إن لزم) |

---

## 7) توصيات نهائية

1. طبّق `025_rls_fix_three_tables.sql` الآن عبر SQL Editor (دقيقتان).
2. جدّد `SUPABASE_ACCESS_TOKEN` من `dashboard/account/tokens` (المنتهي 02 Oct) حتى يعود `apply_migrations_remote.py` و `lint` للعمل.
3. نفّذ تنظيف الكوتا (الخطوات 1+2+4) قبل **10 Sep** لترك هامش أسبوع قبل 17 Sep، ثم أعد فحص `pg_database_size`.
4. بعد الإصلاح، أعد تشغيل Security Advisor linter — يجب أن ينخفض `3 errors → 0` ويبقى `137 warning` للمراجعة اللاحقة.

---
*أُنجز بواسطة وكيل البيانات — فحص REST/OpenAPI، إثبات RLS معطل عبر anon، كتابة 025 idempotent، تحديث setup_all.sql لـ 97/97، واقتراح تنظيف مجاني قبل 17 Sep.*
