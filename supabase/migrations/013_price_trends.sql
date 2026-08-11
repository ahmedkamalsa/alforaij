-- 013_price_trends.sql
-- اتجاهات الأسعار الشهرية: وسيط السعر ووسيط سعر المتر لكل (منطقة × نوع عقار × شهر)
-- يُملأ تلقائيًا يوميًا من الحصاد (market_listings) عبر خطوة persist_price_trends
-- في الوكيل اليومي، ويغذي الرسوم الزمنية في تبويب الأداء (سلسلة أسعار المتر عبر الزمن).
--
-- الوحدة: الشهر بصيغة YYYY-MM (من fetched_at للإعلانات المحصودة). كل صف يمثل
-- وسيطًا شهريًا واحدًا لخلية (منطقة/نوع/شهر) — upsert على المفتاح المركّب حتى
-- لا تتكرر الخلية عند تشغيل الحصاد أكثر من مرة في الشهر نفسه.

create table if not exists public.price_trends (
  id bigint generated always as identity primary key,
  area text not null,
  property_type text not null default '',
  month text not null,                       -- YYYY-MM
  transaction text not null default 'للبيع',
  median_price numeric,                      -- وسيط السعر الإجمالي (د.ك)
  median_price_per_m2 numeric,               -- وسيط سعر المتر (د.ك/م²) — حيثما وُجدت المساحة
  sample_count integer not null default 0,   -- عدد الإعلانات الداخلة في الوسيط
  created_at timestamptz not null default now(),
  unique (area, property_type, month, transaction)
);

create index if not exists price_trends_area_idx on public.price_trends (area, month desc);
create index if not exists price_trends_month_idx on public.price_trends (month desc);

-- RLS: قراءة عامة (لتغذية الرسوم الزمنية في الواجهة/الموقع المرفوع) + كتابة للخدمة فقط.
alter table public.price_trends enable row level security;

create policy "price_trends_anon_read" on public.price_trends
  for select to anon
  using (true);

create policy "price_trends_service_all" on public.price_trends
  for all to service_role
  using (true)
  with check (true);
