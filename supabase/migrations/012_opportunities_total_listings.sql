-- 012_opportunities_total_listings.sql
-- يخزّن اللقطة إجمالي الإعلانات المفحوصة (كل المصادر) منفصلًا عن عدد الفرص المؤهلة،
-- حتى يعرض الواجهة «X فرصة من أصل Y إعلان» بدل X/X عندما تُقرأ اللقطة من القاعدة.

alter table public.opportunities
  add column if not exists total_listings integer not null default 0;
