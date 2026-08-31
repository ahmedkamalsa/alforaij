
-- supabase\migrations\001_initial_schema.sql

create table if not exists listings (
  id bigserial primary key,
  code text unique,
  source text not null default 'alforaij',
  transaction_type text,
  governorate text,
  area text,
  property_type text,
  detail_class text,
  price numeric,
  price_text text,
  space numeric,
  listing_mode text,
  summary text,
  features text,
  published_date date,
  original_url text,
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists saved_reports (
  id bigserial primary key,
  request_text text not null,
  extracted_request jsonb not null,
  report jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists listings_area_idx on listings (area);
create index if not exists listings_type_idx on listings (property_type);
create index if not exists listings_transaction_idx on listings (transaction_type);
create index if not exists listings_price_idx on listings (price);
create index if not exists listings_space_idx on listings (space);



-- supabase\migrations\002_source_quality_and_runs.sql

create table if not exists source_registry (
  id text primary key,
  name text not null,
  category text not null,
  connection text not null,
  role text not null,
  trust_level text not null,
  scoring_policy text not null,
  evidence_policy text not null,
  status text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists source_runs (
  id bigserial primary key,
  source_id text references source_registry(id),
  request_text text,
  request_json jsonb not null default '{}'::jsonb,
  status text not null,
  records_found integer not null default 0,
  records_scored integer not null default 0,
  response_ms numeric,
  source_url text,
  note text,
  error text,
  started_at timestamptz not null default now()
);

create table if not exists listing_evidence (
  id bigserial primary key,
  listing_code text not null,
  source_id text references source_registry(id),
  evidence_type text not null,
  evidence_url text,
  field_name text,
  field_value text,
  confidence numeric,
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists source_runs_source_idx on source_runs (source_id);
create index if not exists source_runs_started_idx on source_runs (started_at desc);
create index if not exists listing_evidence_code_idx on listing_evidence (listing_code);
create index if not exists listing_evidence_source_idx on listing_evidence (source_id);



-- supabase\seed_source_registry.sql

insert into source_registry (
  id,
  name,
  category,
  connection,
  role,
  trust_level,
  scoring_policy,
  evidence_policy,
  status
) values
(
  'alforaij_board',
  'الفريج - بيانات اللوحة المحلية',
  'مصدر أساسي',
  'ملف بيانات محلي',
  'يدخل في البحث والمطابقة والتقييم',
  'مرتفع داخل حدود بيانات الفريج',
  'يدخل في درجة المطابقة والتقييم عند توفر السعر والمساحة والرابط.',
  'كل نتيجة تحتفظ برابط الإعلان الأصلي والحقول الخام عند توفرها.',
  'connected'
),
(
  'opensooq_kw',
  'OpenSooq Kuwait',
  'سوق إعلانات خارجي',
  'بحث حي من صفحة النتائج العامة',
  'يدخل في البحث والتقييم بعد فلترة النوع والمنطقة والعملية',
  'متوسط',
  'لا يدخل الإعلان إلا إذا كان تصنيفه عقاريًا ويطابق الطلب صراحة.',
  'الرابط والسعر والمنطقة والوصف تحفظ كمصدر لكل رقم مستخرج.',
  'live_scored'
),
(
  'mourjan_kw',
  'Mourjan Kuwait',
  'سوق إعلانات خارجي',
  'قراءة HTML من صفحة البحث العامة',
  'يدخل في البحث والتقييم عند وجود كارت إعلان مطابق',
  'متوسط',
  'يتم تحديد نوع العقار من مسار الإعلان، وليس من طلب المستخدم.',
  'الرابط والوصف والسعر الصريح تدخل كدليل عند توفرها.',
  'live_scored'
),
(
  'q8aqar',
  'Q8Aqar',
  'دليل عقاري كويتي',
  'صفحات منطقة ونوع العقار العامة',
  'يدخل فقط عند ظهور رابط إعلان يثبت نفس الطلب',
  'متوسط كرابط دليل، أعلى عند قراءة صفحة التفاصيل',
  'إذا لم يثبت الإعلان أنه نفس المنطقة والنوع والعملية لا يدخل في التقييم.',
  'عند نقص السعر أو المساحة يظهر كرابط دليل ولا يرفع تقييم السعر.',
  'live_conditional'
),
(
  'sakan',
  'Sakan',
  'بوابة بحث عقاري',
  'فحص صفحة البحث العامة',
  'حاليًا دليل توفر فقط وليس تقييم سعر',
  'منخفض للتقييم حتى يتوفر API أو endpoint تفاصيل',
  'لا يدخل في الدرجة إلا بعد استخراج إعلانات تفصيلية قابلة للتحقق.',
  'يعرض عدد المتاح ورابط الصفحة فقط.',
  'availability_only'
),
(
  'official_transactions',
  'الصفقات الرسمية / التسجيل العقاري',
  'مصدر رسمي',
  'استيراد ملف أو API عند توفره',
  'المصدر الأقوى لتقييم السعر عند ربطه',
  'مرتفع جدًا',
  'يستخدم كمرجع سوقي مرجح أعلى من الإعلانات عند توفر صفقات مشابهة.',
  'يجب حفظ رقم وتاريخ الصفقة والمنطقة والنوع والمساحة والسعر.',
  'planned'
)
on conflict (id) do update set
  name = excluded.name,
  category = excluded.category,
  connection = excluded.connection,
  role = excluded.role,
  trust_level = excluded.trust_level,
  scoring_policy = excluded.scoring_policy,
  evidence_policy = excluded.evidence_policy,
  status = excluded.status,
  updated_at = now();

-- supabase\migrations\007_outreach_clicks.sql

-- تتبع نقرات التسويق: كل نقرة «نسخ ملخص» أو «إرسال واتساب» على فرصة/عميل تُسجَّل هنا،
-- وتُجمَّع عدادات التفاعل لكل عميل في تبويب الأداء.
-- سياسات RLS: القراءة والكتابة لدور service_role فقط (أرقام العملاء بيانات خاصة).

create table if not exists outreach_clicks (
  id bigint generated always as identity primary key,
  client_phone text not null default '',
  client_area text not null default '',
  client_type text not null default '',
  opportunity_code text not null default '',
  action text not null default 'copy',
  channel text not null default '',
  created_at timestamptz not null default now()
);

create index if not exists outreach_clicks_phone_idx on outreach_clicks (client_phone);
create index if not exists outreach_clicks_created_idx on outreach_clicks (created_at desc);
create index if not exists outreach_clicks_code_idx on outreach_clicks (opportunity_code);

alter table outreach_clicks enable row level security;

create policy "service read outreach_clicks"
  on outreach_clicks for select to service_role
  using (true);

create policy "service write outreach_clicks"
  on outreach_clicks for insert to service_role
  with check (true);

create policy "service update outreach_clicks"
  on outreach_clicks for update to service_role
  using (true);

create policy "service delete outreach_clicks"
  on outreach_clicks for delete to service_role
  using (true);

-- supabase\migrations\008_search_history.sql

create table if not exists search_history (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  request_text text not null,
  transaction_type text,
  property_type text,
  areas text[] not null default '{}',
  governorates text[] not null default '{}',
  result_count integer not null default 0,
  top_code text,
  top_source text,
  top_area text,
  top_price numeric,
  top_recommendation numeric,
  top_data_quality jsonb not null default '{}'::jsonb,
  source_summary jsonb not null default '[]'::jsonb,
  report_summary text
);

create index if not exists search_history_created_at_idx
  on search_history (created_at desc);

create index if not exists search_history_area_idx
  on search_history using gin (areas);

alter table search_history enable row level security;

create policy "service write search history"
  on search_history for insert to service_role
  with check (true);

create policy "service read search history"
  on search_history for select to service_role
  using (true);

-- =====================================================================
-- 010_market_listings.sql
-- إعلانات السوق الخارجية المحصودة من كل المواقع (Mourjan/OpenSooq/Q8Aqar/...)
-- تُجمع يوميًا عبر الوكيل (خطوة persist_market_listings) فتراكم قاعدة المعرفة
-- كل إعلانات المواقع مثل بيانات الفريج المحلية تمامًا — أساس التحليلات الدقيقة.

create table if not exists public.market_listings (
  id bigint generated always as identity primary key,
  code text not null unique,
  source text,
  transaction text,
  governorate text,
  area text,
  property_type text,
  detail_class text,
  price numeric,
  price_text text,
  space numeric,
  listing_mode text,
  summary text,
  features text,
  published_date text,
  original_url text,
  fetched_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create index if not exists market_listings_area_idx on public.market_listings (area);
create index if not exists market_listings_source_idx on public.market_listings (source);
create index if not exists market_listings_price_idx on public.market_listings (price);
create index if not exists market_listings_fetched_idx on public.market_listings (fetched_at desc);

-- RLS: القراءة/الكتابة لخدمة التطبيق فقط (service_role) — إعلانات السوق جزء من قاعدة المعرفة الداخلية
alter table public.market_listings enable row level security;

create policy "market_listings_service_all" on public.market_listings
  for all
  to service_role
  using (true)
  with check (true);

create policy "market_listings_anon_read" on public.market_listings
  for select
  to anon
  using (true);
-- 014_market_developments.sql
-- تطورات السوق العقاري الكويتي: عناوين وأخبار ومؤشرات تُجمع يوميًا من مصادر
-- إخبارية ومرجعية متخصصة (RSS/صفحات) عبر خطوة discover_market_developments
-- في الوكيل اليومي. تغذي تبويب «التطورات» في المنصة بحيث يظهر الجديد من
-- السوق (أسعار/تنظيم/تمويل/مشاريع) إلى جانب بيانات الإعلانات نفسها.
--
-- المفتاح: url فريد — إعادة التشغيل اليومي تحديث لا تكرار.

create table if not exists public.market_developments (
  id bigint generated always as identity primary key,
  url text not null unique,
  title text not null,
  source text not null default '',          -- معرّف المصدر (kuna / kuwaittimes / ...)
  source_name text not null default '',     -- الاسم العربي الظاهر
  category text not null default 'سوق عقاري',
  published text not null default '',       -- تاريخ النشر كما ورد في التغذية (YYYY-MM-DD إن توفر)
  summary text not null default '',
  fetched_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create index if not exists market_developments_fetched_idx on public.market_developments (fetched_at desc);
create index if not exists market_developments_category_idx on public.market_developments (category);

-- RLS: قراءة عامة (للعرض في المنصة/الموقع المرفوع) + كتابة للخدمة فقط.
alter table public.market_developments enable row level security;

create policy "market_developments_anon_read" on public.market_developments
  for select to anon
  using (true);

create policy "market_developments_service_all" on public.market_developments
  for all to service_role
  using (true)
  with check (true);

-- =====================================================================
-- 024_ai_agents_audit.sql
-- Audit trail for AI providers, analysis agents, partner feeds, and data quality.

create table if not exists public.ai_provider_runs (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  request_text text not null default '',
  provider text not null,
  model text not null default '',
  status text not null,
  response_ms numeric,
  error text,
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.analysis_agent_runs (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  request_text text not null default '',
  agent_id text not null,
  agent_name text not null,
  status text not null,
  summary text not null default '',
  outputs jsonb not null default '{}'::jsonb
);

create table if not exists public.analysis_agent_steps (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  request_text text not null default '',
  agent_id text not null,
  step_key text not null,
  step_value jsonb not null default '{}'::jsonb
);

create table if not exists public.partner_feeds (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  source_id text references public.source_registry(id),
  source_name text not null,
  access_model text not null default 'partner_required',
  status text not null default 'planned',
  endpoint_url text,
  contract_note text,
  last_checked_at timestamptz,
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.data_quality_events (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  request_text text not null default '',
  source_id text references public.source_registry(id),
  listing_code text,
  event_type text not null,
  severity text not null default 'info',
  reason text not null default '',
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists ai_provider_runs_created_idx on public.ai_provider_runs (created_at desc);
create index if not exists ai_provider_runs_provider_idx on public.ai_provider_runs (provider, status);
create index if not exists analysis_agent_runs_created_idx on public.analysis_agent_runs (created_at desc);
create index if not exists analysis_agent_runs_agent_idx on public.analysis_agent_runs (agent_id, status);
create index if not exists analysis_agent_steps_agent_idx on public.analysis_agent_steps (agent_id, created_at desc);
create index if not exists partner_feeds_source_idx on public.partner_feeds (source_id, status);
create index if not exists data_quality_events_source_idx on public.data_quality_events (source_id, severity);
create index if not exists data_quality_events_listing_idx on public.data_quality_events (listing_code);

alter table public.ai_provider_runs enable row level security;
alter table public.analysis_agent_runs enable row level security;
alter table public.analysis_agent_steps enable row level security;
alter table public.partner_feeds enable row level security;
alter table public.data_quality_events enable row level security;

create policy "ai_provider_runs_service_all" on public.ai_provider_runs
  for all to service_role
  using (true)
  with check (true);

create policy "analysis_agent_runs_service_all" on public.analysis_agent_runs
  for all to service_role
  using (true)
  with check (true);

create policy "analysis_agent_steps_service_all" on public.analysis_agent_steps
  for all to service_role
  using (true)
  with check (true);

create policy "partner_feeds_service_all" on public.partner_feeds
  for all to service_role
  using (true)
  with check (true);

create policy "data_quality_events_service_all" on public.data_quality_events
  for all to service_role
  using (true)
  with check (true);
