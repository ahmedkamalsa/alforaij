-- تنبيهات الفرص للمستخدمين المحفوظين (المهمة 3): الجرس داخل التطبيق + أساس واتساب.
--
-- صف لكل (سرّ × فرصة) — قيد unique يمنع التكرار حتى عند إعادة تشغيل السكربت
-- (منع التشغيل المزدوج على مستوى القاعدة نفسها، فوق فحص Python).
-- الكتابة (من السكربت اليومي) عبر service_role؛ القراءة/التعليم كمقروء عبر دوال
-- RPC محروسة بالسرّ (نفس نمط saved_searches).

create table if not exists user_alerts (
  id bigint generated always as identity primary key,
  user_secret text not null,               -- مفتاح الملكية (لا يُكشف)
  opportunity_code text not null,
  area text,
  price numeric,
  change text not null,                    -- new | price_drop
  message text not null,                   -- النص الجاهز (أساس قالب واتساب)
  url text not null default '',            -- رابط «فتح الفرصة» في الجرس
  seen boolean not null default false,
  created_at timestamptz not null default now(),
  unique (user_secret, opportunity_code)
);

alter table user_alerts enable row level security;

drop policy if exists "user alerts service role all" on user_alerts;
create policy "user alerts service role all"
  on user_alerts for all to service_role using (true) with check (true);

-- قائمة تنبيهات المستخدم (الأحدث أولًا) — يرفض السرّ غير المسجّل
create or replace function list_user_alerts(p_secret text)
returns table (
  id bigint,
  opportunity_code text,
  area text,
  price numeric,
  change text,
  message text,
  url text,
  seen boolean,
  created_at timestamptz
)
language plpgsql
security definer
stable
as $$
begin
  if not search_owner_exists(p_secret) then
    raise exception 'invalid secret';
  end if;
  return query
    select ua.id, ua.opportunity_code, ua.area, ua.price, ua.change,
           ua.message, ua.url, ua.seen, ua.created_at
    from user_alerts ua
    where ua.user_secret = p_secret
    order by ua.created_at desc;
end;
$$;

-- تعليم كل التنبيهات كمقروءة — يرفض السرّ غير المسجّل
create or replace function mark_alerts_seen(p_secret text)
returns bigint
language plpgsql
security definer
as $$
declare
  v_count bigint;
begin
  if not search_owner_exists(p_secret) then
    raise exception 'invalid secret';
  end if;
  update user_alerts set seen = true
  where user_secret = p_secret and not seen;
  get diagnostics v_count = row_count;
  return v_count;
end;
$$;

revoke all on function list_user_alerts(text) from public;
revoke all on function mark_alerts_seen(text) from public;
grant execute on function list_user_alerts(text) to anon, service_role;
grant execute on function mark_alerts_seen(text) to anon, service_role;
