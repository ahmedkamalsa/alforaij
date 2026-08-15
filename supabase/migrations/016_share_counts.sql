-- عداد مشاركات بطاقات التقييم: كل مشاركة «إرسال واتساب» لتقييم (رمز فرصة/إعلان) تُزيد
-- عدّادها هنا — يُقرأ ويُزاد مباشرة من الواجهة المرفوعة عبر REST العام (مثل عدّادات
-- القاعدة الحية)، فلا يعتمد على خادم API.
--
-- الأمان مقصود هنا: العدّاد مقياس شعبية عام (بلا هوية)، لذا يُسمح لـ anon بالقراءة
-- والزيادة عبر دالة ذرّية — لا يُسمح له بالكتابة المباشرة أو الحذف.

create table if not exists share_counts (
  opportunity_code text primary key,
  count bigint not null default 0,
  updated_at timestamptz not null default now()
);

alter table share_counts enable row level security;

drop policy if exists "anon read share_counts" on share_counts;
create policy "anon read share_counts"
  on share_counts for select to anon
  using (true);

drop policy if exists "anon update share_counts" on share_counts;
create policy "anon update share_counts"
  on share_counts for update to anon
  using (true);

-- دالة زيادة ذرّية: المنصة تُنشئ الصف عند أول مشاركة وتزيد العدّاد بعدها بلا تعارض.
create or replace function increment_share(p_code text)
returns void
language sql
security definer
as $$
  insert into share_counts (opportunity_code, count, updated_at)
  values (p_code, 1, now())
  on conflict (opportunity_code)
  do update set count = share_counts.count + 1, updated_at = now()
$$;

revoke all on function increment_share(text) from public;
grant execute on function increment_share(text) to anon;
grant execute on function increment_share(text) to service_role;
