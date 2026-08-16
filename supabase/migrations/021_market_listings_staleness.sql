-- 021_market_listings_staleness.sql
-- معالجة الإعلانات القديمة/المباعة (جودة البيانات):
-- كل إعلان محصود يحمل آخر ظهور (last_seen_at) وحالة (active/stale).
-- الوكيل اليومي يحدّث last_seen_at لكل إعلان يظهر مجددًا في الحصاد (ويردّه active)،
-- ويكسح stale كل إعلان لم يُرَ منذ مدة (افتراضيًا 14 يومًا) — فيبقى في قاعدة
-- المعرفة للتاريخ والتقييم ولا يُعرض في اللوحة/الفرص/المؤشرات (تُقرأ active فقط).

alter table public.market_listings
  add column if not exists last_seen_at timestamptz not null default now();

alter table public.market_listings
  add column if not exists status text not null default 'active';

-- الاكتشاف السريع للمرشّحين للكسح (status, last_seen_at)
create index if not exists market_listings_status_seen_idx
  on public.market_listings (status, last_seen_at desc);
