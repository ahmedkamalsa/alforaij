-- 015_listing_phone.sql
-- رقم تواصل المعلن لكل إعلان سوق — يُستخرج من صفحة تفاصيل الإعلان
-- (روابط wa.me/tel أو JSON مضمّن في 4Sale/Mourjan/Q8Aqar) عبر وكيل إكمال
-- التفاصيل، فيظهر زر «تواصل واتساب» مباشرة في بطاقة الإعلان.

alter table public.market_listings
  add column if not exists phone text;

create index if not exists market_listings_phone_idx on public.market_listings (phone)
  where phone is not null and phone <> '';
