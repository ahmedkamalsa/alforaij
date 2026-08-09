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
