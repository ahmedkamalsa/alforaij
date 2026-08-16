-- محفظة المستثمر المجانية (اقتراح «لوحة إدارة المحافظ»): سجّل عقاراتك وتتبّع
-- قيمتها السوقية التقديرية وعائدها — ضمن خطة الحسابات المجاني.
--
-- الوصول كله عبر دوال RPC تتحقق من سرّ المستخدم (users.secret) — لا قراءة ولا
-- كتابة مباشرة من anon — بنمط البحث المحفوظ (018_saved_searches.sql).

create table if not exists portfolios (
  id bigint generated always as identity primary key,
  user_secret text not null,               -- مفتاح الملكية (لا يُكشف)
  code text not null unique,
  area text not null,
  governorate text not null default '',
  property_type text not null default '',
  space numeric,
  purchase_price numeric,
  purchase_date text,
  monthly_rent numeric,
  note text not null default '',
  created_at timestamptz not null default now()
);

alter table portfolios enable row level security;

drop policy if exists "portfolios service role all" on portfolios;
create policy "portfolios service role all"
  on portfolios for all to service_role using (true) with check (true);

-- هل السرّ مسجّل ومؤكد؟ (يستخدمه دوال المحفظة داخليًا — لا يُمنح لـ anon مباشرة)
create or replace function portfolio_owner_exists(p_secret text)
returns boolean
language sql
security definer
stable
as $$
  select exists (select 1 from users where secret = p_secret and verified)
$$;

-- إضافة عقار إلى المحفظة
create or replace function save_portfolio_item(
  p_secret text,
  p_area text,
  p_governorate text default '',
  p_property_type text default '',
  p_space numeric default null,
  p_purchase_price numeric default null,
  p_purchase_date text default '',
  p_monthly_rent numeric default null,
  p_note text default ''
) returns bigint
language plpgsql
security definer
as $$
declare
  v_id bigint;
  v_code text;
begin
  if not portfolio_owner_exists(p_secret) then
    raise exception 'invalid secret';
  end if;
  if nullif(trim(p_area), '') is null then
    raise exception 'area is required';
  end if;
  v_code := 'PF-' || upper(substr(replace(md5(random()::text || clock_timestamp()::text), '-', ''), 1, 10));
  insert into portfolios (
    user_secret, code, area, governorate, property_type,
    space, purchase_price, purchase_date, monthly_rent, note
  ) values (
    p_secret, v_code, trim(p_area), coalesce(p_governorate, ''), coalesce(p_property_type, ''),
    p_space, p_purchase_price, coalesce(p_purchase_date, ''), p_monthly_rent, coalesce(p_note, '')
  )
  returning id into v_id;
  return v_id;
end;
$$;

-- قائمة عقارات المستخدم (الأحدث أولًا) — بلا حقل السرّ نفسه؛ يرفض السرّ غير المسجّل
create or replace function list_portfolio_items(p_secret text)
returns table (
  id bigint,
  code text,
  area text,
  governorate text,
  property_type text,
  space numeric,
  purchase_price numeric,
  purchase_date text,
  monthly_rent numeric,
  note text,
  created_at timestamptz
)
language plpgsql
security definer
stable
as $$
begin
  if not portfolio_owner_exists(p_secret) then
    raise exception 'invalid secret';
  end if;
  return query
    select p.id, p.code, p.area, p.governorate, p.property_type,
           p.space, p.purchase_price, p.purchase_date, p.monthly_rent, p.note, p.created_at
    from portfolios p
    where p.user_secret = p_secret
    order by p.created_at desc;
end;
$$;

-- حذف عقار (فقط ما يملكه السرّ — يرفض السرّ غير المسجّل)
create or replace function delete_portfolio_item(p_secret text, p_id bigint)
returns boolean
language plpgsql
security definer
as $$
begin
  if not portfolio_owner_exists(p_secret) then
    raise exception 'invalid secret';
  end if;
  delete from portfolios where id = p_id and user_secret = p_secret;
  return found;
end;
$$;

revoke all on function portfolio_owner_exists(text) from public;
revoke all on function save_portfolio_item(text, text, text, text, numeric, numeric, text, numeric, text) from public;
revoke all on function list_portfolio_items(text) from public;
revoke all on function delete_portfolio_item(text, bigint) from public;

grant execute on function portfolio_owner_exists(text) to service_role;
grant execute on function save_portfolio_item(text, text, text, text, numeric, numeric, text, numeric, text) to anon, service_role;
grant execute on function list_portfolio_items(text) to anon, service_role;
grant execute on function delete_portfolio_item(text, bigint) to anon, service_role;
