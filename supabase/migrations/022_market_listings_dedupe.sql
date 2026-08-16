-- 022_market_listings_dedupe.sql
-- كسح شبه التكرار بحذر (جودة البيانات):
-- الإعلان المُعاد جَلْبه برمز مختلف (تغيّر الرابط/المعرف بين جلسات الحصاد) يُوسم
-- duplicate ويُحال إلى نظيره المحتفظ به (duplicate_of) — دون حذف أي تاريخ.
-- البوابة دقيقة: تطابق تام (المصدر + المنطقة + نوع العقار + السعر + العنوان
-- المطبع) + اتساق هاتف المعلن والمساحة؛ الوحدات المتشابهة شرعيًا تبقى منفصلة.

alter table public.market_listings
  add column if not exists duplicate_of text;

create index if not exists market_listings_duplicate_idx
  on public.market_listings (status, duplicate_of)
  where status = 'duplicate';
