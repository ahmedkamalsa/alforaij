# خطة نظام الحسابات المجاني: تسجيل بالهاتف + بحث محفوظ + تنبيهات واتساب مطابقة

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** تحويل الزائر إلى مستخدم دائم عبر حساب مجاني برقم الهاتف (بدون كلمة مرور)، مع البحث المحفوظ والتنبيه الفوري عند نزول فرصة مطابقة — «اللقطة قبل المنافسين». كل الميزات مجانية، وأرقام الواتساب المُجمَّعة هي الأصل الأغلى للمنصة.

**Architecture:** ثلاث طبقات فوق البنية القائمة دون أي اعتماد جديد:
1. **الهوية (OTP بالهاتف):** جدول `users` + رمز تحقق لمرة واحدة (6 أرقام، sha256+salt، انتهاء 10 دقائق). التسليم عبر **WhatsApp Cloud API (Meta)** برسالة قالب مجانية إن وُجدت الأسرار، وإلا انحدار أنيق: الرمز يظهر على الشاشة مع رابط wa.me للتأكيد اليدوي — نفس فلسفة «البوابة تحذّر لا تنكسر».
2. **البحث المحفوظ:** جدول `saved_searches` يُدار عبر دوال RPC تتحقق من سرّ المستخدم (نفس نمط `increment_share` المُثبَت) — يعمل على الموقع الثابت المنشور (GH Pages/Cloudflare) مباشرة عبر anon REST، بلا خادم وسيط.
3. **خط أنابيب التنبيه:** إعادة استخدام منطق `build_whatsapp_alerts` (المطابقة الموجودة) مع تعميمه من `client_leads` إلى `saved_searches`، وتخزين التنبيهات في `user_alerts`، وتسليمها عبر قالب واتساب من الوكيل اليومي (cron 03:00 UTC) — مع بقاء الجرس داخل التطبيق كقناة دائمة تعمل دائمًا.

**Tech Stack:** لا جديد. Python 3.11 stdlib (hashlib للـ OTP، urllib لنداءات Meta)، Supabase عبر anon REST + service_role (النمطان الموجودان: `share_counts`/`increment_share` للعميل، `persist_to_supabase.py` للخادم)، واجهة vanilla JS بلا بناء. بوابة الاختبارات: pytest + sprint + جوال + أداء (كما في المهام السابقة).

## Global Constraints

- **لا Tailwind ولا npm ولا build step** — المشروع متعمد بلا اعتماديات؛ كل شيء stdlib + Supabase REST.
- **كل نداء Supabase من المتصفح يجب أن يكون محروسًا** بوجود `SUPABASE_URL`/المفتاح (نمط `shareCountsBase()`): أي 404 مسجَّل في الكونسول يُسقط فحص الجوال في CI (درس عداد المشاركة — `fix(share): load share counters only in static mode`). الفشل يُبتلع صامتًا دائمًا.
- **السرّ هو المصداقية:** `users.secret` (24 حرفًا عشوائيًا يُولَّد عند التسجيل) هو المفتاح الوحيد لقراءة/تعديل بيانات المستخدم — لا يُكشف أبدًا، ويُحفظ في `localStorage` فقط. دوال RPC ترفض أي نداء بلا سرّ مطابق.
- **رقم الهاتف يُوحَّد** عبر `normalize_phone` الموجود في `backend/services/opportunities.py` (صيغة `+965XXXXXXXX`) — أي خرق للتنسيق (مثل `0106...`) يُرفض عند التسجيل.
- **رسائل واتساب التجارية** (التي يبدأها الخادم) يجب أن تمر عبر **قالب معتمد** في Cloud API — النص العربي الجاهز في `build_whatsapp_alerts` هو أساس القالب (مع استبدال `[اسمك]`). بدون أسرار واتساب: التنبيهات تتراكم داخل التطبيق (الجرس) ولا تُرسل — انحدار أنيق موثّق، لا فشل.
- **البيانات الحساسة:** `phone` يُخزَّن عاديًا (مطلوب للتسليم)، لكن الاستعلامات العامة لا تكشف سوى عدّادات مجمّعة — لا قائمة أرقام. جداول `client_leads` (الوسيط) تبقى منفصلة تمامًا عن `users` (المستخدمون).
- حقائق بيئة الاختبار: pytest الكامل = `PYTHONIOENCODING=utf-8 python -m pytest tests/ -q` على **Python 3.11** (`/c/Users/hello/AppData/Local/Programs/Python/Python311/python`)؛ واجهة الفحص تحتاج خادمًا حيًا على 8000؛ sprint = `tests/playwright/testsprint_audit.py` (33)، جوال = `scripts/run_mobile_checks.py`، أداء = `tests/playwright/performance_audit.py` (ملاحظة: فحص الكاش فيه زحف زمني معروف — أعد التشغيل عند فشل عابر).
- حالة العمل: شجرة العمل تحمل عمل الراديوس غير الملتزم (`styles.css` + `scripts/radius_*.py` + `tests/test_radius_*.py`) وملفات `data/*.json` اليومية — **لا تُضمّن في التزامات هذه الخطة**؛ التزم جراحيًا ملفات الخطة فقط (درس الدفع عبر worktree: البعيد قد يتقدم بالتزامات يومية على `data/*` — تحقق بـ `git fetch` قبل الدفع، وادفع عبر `git worktree` مؤقت عند أي تعارض على ملفات البيانات).

---

### Task 1: الهوية — جدول `users` + OTP + نقاط التسجيل والتحقق

**Files:**
- Create: `supabase/migrations/017_users_otp.sql`
- Create: `backend/services/accounts.py` (منطق OTP: توليد/تجزئة/تحقق/محاولات — نقي قابل للاختبار بلا شبكة)
- Modify: `backend/main.py` (نقطتان: `POST /api/register`، `POST /api/verify-otp` — بنمط `POST /api/clients` الموجود)
- Create: `scripts/send_whatsapp_message.py` (مرسل Cloud API: template message؛ no-op صامت عند غياب الأسرار)
- Test: `tests/test_accounts.py`

**Interfaces:**
- `users` schema:
  ```sql
  create table if not exists users (
    id bigint generated always as identity primary key,
    phone text not null unique,              -- بصيغة +965XXXXXXXX
    secret text not null,                    -- 24 حرفًا عشوائيًا = المصداقية
    otp_hash text, otp_expires_at timestamptz,
    otp_attempts integer not null default 0,
    verified boolean not null default false,
    last_alert_at timestamptz,
    created_at timestamptz not null default now()
  );
  alter table users enable row level security;
  -- anon: insert فقط (تسجيل)، select على صفّه عبر rpc فقط — لا select مباشر
  ```
- `POST /api/register` `{phone}` → يوحِّد الرقم، يرفض غير الكويتي، يُصدر OTP (6 أرقام، sha256+ملح، 10 دقائق، حد 5 محاولات/15 دقيقة)، يُسلِّمه عبر `send_whatsapp_message` (قالب `otp_template`) أو يعيد `delivery: "on_screen"` مع رمز لمرة واحدة للانحدار.
- `POST /api/verify-otp` `{phone, code}` → يصحح المحاولات/الانتهاء، يُنشئ `secret` عشوائيًا (إن لم يكن موجودًا) ويرجع `{secret, phone}`.
- إعادة الإرسال: `POST /api/register` مرة ثانية يبطل الرمز القديم ويصدر جديدًا.

- [ ] **Step 1: كتابة الاختبار الفاشل** — `tests/test_accounts.py`: توحيد الرقم، رفض `0106...`/الرقم الأجنبي، OTP صحيح/خاطئ/منتهي، حد المحاولات، السرّ عشوائي وطوله، إعادة الإرسال تبطل القديم.
- [ ] **Step 2: migration 017** + تطبيقها على المشروع البعيد عبر إدارة Supabase (نمط `016_share_counts.sql` و`scripts/apply_migrations_remote.py`).
- [ ] **Step 3: `backend/services/accounts.py`** — دوال نقية (توليد/تحقق) + `backend/main.py` النقطتان.
- [ ] **Step 4: `scripts/send_whatsapp_message.py`** — نداء Cloud API عبر `urllib`؛ يقرأ `WHATSAPP_TOKEN`/`WHATSAPP_PHONE_ID` من البيئة؛ يطبع تحذيرًا ويعيد `None` عند الغياب.
- [ ] **Step 5: إثبات الحي** — تسجيل عبر الخادم المحلي (8000) برقم اختباري، تحقق، وإعادة إنتاج انحدار `on_screen` بلا أسرار. pytest الجديد أخضر.
- [ ] **Step 6: الالتزام الأول** (`feat(accounts): phone OTP registration`) — جراحي، بدون الراديوس/البيانات.

---

### Task 2: البحث المحفوظ — جدول + دوال RPC + حفظ/قائمة من الواجهة

**Files:**
- Create: `supabase/migrations/018_saved_searches.sql` (جدول + دوال RPC `security definer`)
- Modify: `frontend/app.js` (زر «حفظ البحث وتنبيهي عند النزول» في شريط النتائج + لوحة «بحثي المحفوظ» + وحدة `accountState` في `localStorage`)
- Test: `tests/test_saved_searches.py` (دوال المطابقة النقية)

**Interfaces:**
- `saved_searches` schema:
  ```sql
  create table if not exists saved_searches (
    id bigint generated always as identity primary key,
    user_secret text not null,               -- مفتاح الملكية (بدون FK — السرّ لا يُكشف بمعرّف)
    name text not null,
    request_text text not null default '',
    transaction_type text, property_type text,
    areas text[] not null default '{}', governorates text[] not null default '{}',
    price_min numeric, price_max numeric,
    alert_enabled boolean not null default true,
    last_matched_at timestamptz,
    created_at timestamptz not null default now()
  );
  alter table saved_searches enable row level security;
  ```
- RPC (نمط `increment_share` — anon يمرر السرّ كمعامل):
  - `rpc/save_search(p_secret, p_name, p_request, p_transaction, p_property, p_areas, p_govs, p_min, p_max)` → يتحقق من `users.secret` ثم يُدخل/يحدّث.
  - `rpc/list_saved_searches(p_secret)` → صفوف المستخدم فقط (الجدول نفسه بلا select مباشر).
  - `rpc/delete_saved_search(p_secret, p_id)` و`rpc/set_search_alert(p_secret, p_id, p_enabled)`.
- الواجهة: من الفلاتر الحالية في صفحة البحث (نوع العملية/العقار/المناطق/المحافظات/السعر) تُبنى الحمولة؛ بدون حساب → يفتح نافذة «حسابي». قائمة «بحثي المحفوظ»: تبديل التنبيه/حذف، مع تمييز بصري أن التنبيه «نشط».

- [ ] **Step 1: اختبار فاشل** — `test_saved_searches.py`: دالة `match_search_to_item` (تطابق منطقة/نوع/ميزانية مع فرصة) — إعادة استخدام منطق مطابقة العملاء في `market_analysis.py` مع معايير البحث المحفوظ.
- [ ] **Step 2: migration 018 + دوال RPC** + تطبيق + إثبات anon REST (قراءة/حفظ/حذف/تبديل برمز تجريبي ثم تنظيف).
- [ ] **Step 3: الواجهة** — `accountState` (السرّ من localStorage)، زر الحفظ، لوحة القائمة. **كل نداء Supabase محروس** بنمط `shareCountsBase()` — صفر 404 ممكن.
- [ ] **Step 4: إثبات المتصفح** — تسجيل → حفظ بحث → إعادة تحميل → القائمة باقية (نجاة من الـ reload مثل عداد المشاركة). صفر أخطاء كونسول.
- [ ] **Step 5: البوابات الجزئية** — pytest + sprint على الخادم المحلي.
- [ ] **Step 6: الالتزام الثاني** (`feat(accounts): save searches with match scoring`).

---

### Task 3: خط التنبيه — مطابقة `saved_searches` + `user_alerts` + التسليم من الوكيل اليومي

**Files:**
- Create: `supabase/migrations/019_user_alerts.sql` (جدول + RPC)
- Create: `scripts/send_opportunity_alerts.py` (يمتد من `build_whatsapp_alerts` لكن لمطابقة الباحثين المحفوظين)
- Modify: `.github/workflows/daily-data-update.yml` (خطوة بعد الحصاد: `send_opportunity_alerts`)
- Test: `tests/test_opportunity_alerts.py`

**Interfaces:**
- `user_alerts` schema:
  ```sql
  create table if not exists user_alerts (
    id bigint generated always as identity primary key,
    user_secret text not null,
    opportunity_code text not null, area text, price numeric,
    change text not null,                    -- new | price_drop
    message text not null,                   -- النص الجاهز (أساس قالب واتساب)
    seen boolean not null default false,
    created_at timestamptz not null default now()
  );
  -- RPC: rpc/list_user_alerts(p_secret) (الأحدث أولًا)، rpc/mark_alerts_seen(p_secret)
  ```
- `scripts/send_opportunity_alerts.py` — يعمل **بعد** الحصاد اليومي، ويقرأ لقطتَي الفرص (السابقة/الحالية) من `data/`:
  1. `new`/`price_drop` في الطبقة اليومية (نفس فرق `build_whatsapp_alerts`).
  2. لكل تغيير: جلب `saved_searches` من Supabase (service_role) واختيار المطابقات عبر دالة المطابقة من Task 2.
  3. بناء الرسالة لكل مستخدم (تخصيص بمنطقته/نوعه/ميزانيته — نمط `oppClientSendLinks`)، وكتابة صف `user_alerts`.
  4. إن وُجدت أسرار واتساب: إرسال قالب `alert_template` (مع `opportunity` و`area` و`price` و`link` كمتغيرات)؛ وإلا: يكتفي بالجرس ويطبع تحذيرًا.
  5. **منع التكرار:** لا يُرسل تنبيه لنفس `user_secret + opportunity_code` إلا مرة واحدة (فحص قبل الإدراج).
- الواجهة (مع Task 4): جرس 🔔 مع عدّاد غير مقروء → قائمة التنبيهات → «تم» يعلّم الكل مقروءًا.

- [ ] **Step 1: اختبار فاشل** — `test_opportunity_alerts.py`: تكامل `send_opportunity_alerts` بثنائية لقطات اصطناعية (فرصة جديدة تطابق بحثًا محفوظًا → صف تنبيه بالرسالة الصحيحة؛ انخفاض سعر → `price_drop`؛ لا تكرار عند التشغيل المزدوج).
- [ ] **Step 2: migration 019 + RPC** + تطبيق + إثبات anon (قائمة/تمّ).
- [ ] **Step 3: السكربت** + ربطه في `daily-data-update.yml` بعد الحصاد (أسرار: `SUPABASE_*` موجودة + `WHATSAPP_*` اختيارية). تشغيل يدوي مرة على بيئة اختبار للتحقق من الصفوف.
- [ ] **Step 4: إثبات الحي** — إدراج بحث محفوظ اصطناعي → تشغيل السكربت → تنبيه في الجرس عبر anon REST.
- [ ] **Step 5: الالتزام الثالث** (`feat(alerts): match saved searches, store + deliver alerts`).

---

### Task 4: واجهة الحساب + الجرس + البوابات الكاملة + النشر

**Files:**
- Modify: `frontend/app.js` (نافذة «حسابي»، زر حفظ البحث، جرس التنبيهات، دمج `accountState`)
- Modify: `frontend/styles.css` (تنسيقات النافذة/الجرس بتوكينات `--radius-*`/`--muted` الموجودة — **دون لمس عمل الراديوس غير الملتزم**)
- Modify: `frontend/index.html` (رفع `?v=20260816-free-accounts`)
- Modify: `docs/NETLIFY_SETUP.md` أو `docs/AGENT_CONTEXT.md` (توثيق أسرار واتساب الاختيارية)
- Test: `tests/playwright/_probe_accounts.py` (تدفق كامل: تسجيل → حفظ → تنبيه → تمّ)

**Interfaces:**
- نافذة «حسابي»: إدخال هاتف → «أرسل الرمز» → (عرض 6 خانات) → تحقق → حالة «مسجَّل ✓ — تنبيهات مفعلة». عند `delivery: "on_screen"` تُعرض رسالة «الرمز سيصل عبر واتساب/يدويًا» حسب الوضع.
- زر «🔔 حفظ البحث وتنبيهي» في شريط نتائج البحث: يلتقط الفلاتر الحالية، يتطلب تسجيلًا، يؤكد «تم الحفظ — سننبّهك عند نزول فرصة مطابقة».
- الجرس في الشريط العلوي: عدّاد أحمر بعدد غير المقروء، قائمة منسدلة (الفرصة/المنطقة/السعر/التغيير + «فتح الفرصة» و«تم»).
- **قاعدة الفحص:** أي رحلة متصفح تنتهي بصفر أخطاء كونسول — النداءات الفاشلة تُبتلع (الدرس من فحص الجوال).

- [ ] **Step 1: نافذة الحساب** + دمج `accountState` (نجاة من reload عبر localStorage).
- [ ] **Step 2: زر الحفظ + قائمة «بحثي المحفوظ»** (تبديل/حذف).
- [ ] **Step 3: الجرس** (عدّاد + قائمة + تمّ) — محروس بنمط `shareCountsBase`.
- [ ] **Step 4: `_probe_accounts.py`** — تدفق كامل على الخادم المحلي + صفر كونسول؛ ثم تشغيله على الموقع الحي بعد النشر.
- [ ] **Step 5: البوابات الكاملة** — pytest كامل (المتوقع 312 + ~18 جديدًا)، sprint 33/33، فحص الجوال، الأداء (أعد تشغيل فحص الكاش عند الزحف العابر).
- [ ] **Step 6: التوثيق + الالتزام الرابع** (`feat(accounts): account modal + alert bell`) — ثم **دفع واحد** (تحقق `git fetch` من تقدم البعيد أولًا؛ worktree مؤقت عند تعارض `data/*`)، ومتابعة كل workflows حتى الخضراء، والتحقق الحي (إصدار `?v=` + تدفق الحساب بمتصفح حقيقي).

---

## جدول الأسرار الجديدة (اختيارية — كل شيء يعمل بدونها)

| السر | الغرض | مصدره | بدونها |
|---|---|---|---|
| `WHATSAPP_TOKEN` | رمز واجهة Meta Cloud API | developers.facebook.com → تطبيقك | OTP يظهر على الشاشة + تأكيد يدوي عبر wa.me |
| `WHATSAPP_PHONE_ID` | رقم الهاتف المرسِل في Cloud API | إعدادات التطبيق (رقم منفصل عن رقمك الشخصي) | نفسه |
| `WHATSAPP_OTP_TEMPLATE` | اسم قالب رمز التحقق (معتمد في Meta) | إدارة القوالب | نفسه |
| `WHATSAPP_ALERT_TEMPLATE` | اسم قالب تنبيه الفرصة (متغيرات: فرصة/منطقة/سعر/رابط) | إدارة القوالب | التنبيهات تتراكم في الجرس فقط |

الإضافة عبر `gh secret set <NAME>` في طرفية المستخدم (نمط أسرار Netlify/Cloudflare — القيم لا تمر عبر الدردشة).

## بوابة الرجوع

- التزامات الخطة كلها إضافية (جداول/دوال/نقاط/زر/جرس) — `git revert` نظيف بلا تعارض.
- بدون أسرار واتساب تبقى المنصة **كاملة الوظائف** (OTP على الشاشة، تنبيهات في الجرس) — الانحدار موثّق في الاختبارات لا مجرد وعد.
- فحص التراجع (نمط بوابة الراديوس): `git revert` في worktree مؤقت، تأكيد حذف أدوات الميزة وعودة `app.js` لمحتوى ما قبلها، ثم تنظيف.
