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
