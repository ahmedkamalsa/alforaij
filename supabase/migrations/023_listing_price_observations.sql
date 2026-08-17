-- 023_listing_price_observations.sql
-- سجل سعر العقار: ملاحظة سعر لكل إعلان عند كل ظهور في الحصاد اليومي (append-only).
-- كل تشغيل للوكيل يسجّل سعر كل إعلان محصود — يبني «تاريخ العقار» ويكشف
-- الإعلانات الوهمية (تذبذب سعر بلا مبرر) ويمدّ تنبيهات الانخفاض بالسياق.
-- لا حذف أبدًا: الصفوف تتراكم كقاعدة معرفة، والواجهة تطوي الأسعار المتكررة.
--
-- ملاحظة: الاسم listing_price_observations (وليس listing_price_history) لأن
-- اسم history محجوز في القاعدة الحية بجدول قديم يتيم (old_price/new_price/
-- changed_at) لا يستخدمه أي كود — تُرك دون مساس.

create table if not exists public.listing_price_observations (
  id bigint generated always as identity primary key,
  code text not null,
  source text,
  area text,
  property_type text,
  transaction text,
  price numeric,
  price_text text,
  seen_at timestamptz not null default now(),
  created_at timestamptz not null default now()
);

create index if not exists listing_price_observations_code_seen_idx
  on public.listing_price_observations (code, seen_at desc);

alter table public.listing_price_observations enable row level security;

create policy "listing_price_observations_service_all" on public.listing_price_observations
  for all
  to service_role
  using (true)
  with check (true);

-- القراءة العامة: السعر التاريخي للإعلان معلومة سوق عامة (مثل market_listings نفسها)
create policy "listing_price_observations_anon_read" on public.listing_price_observations
  for select
  to anon
  using (true);
