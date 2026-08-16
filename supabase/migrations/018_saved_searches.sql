-- البحث المحفوظ (المهمة 2): حسابات مجانية — احفظ بحثك ونبّهك عند نزول فرصة مطابقة.
--
-- الوصول كله عبر دوال RPC تتحقق من سرّ المستخدم (users.secret) — لا قراءة ولا
-- كتابة مباشرة من anon. السرّ هو مفتاح الملكية (بلا FK إلى users حتى لا يُكشف
-- بمعرّف رقمي يمكن تخمينه).

create table if not exists saved_searches (
  id bigint generated always as identity primary key,
  user_secret text not null,               -- مفتاح الملكية (لا يُكشف)
  name text not null,
  request_text text not null default '',
  transaction_type text,
  property_type text,
  areas text[] not null default '{}',
  governorates text[] not null default '{}',
  price_min numeric,
  price_max numeric,
  alert_enabled boolean not null default true,
  last_matched_at timestamptz,
  created_at timestamptz not null default now()
);

alter table saved_searches enable row level security;

drop policy if exists "saved searches service role all" on saved_searches;
create policy "saved searches service role all"
  on saved_searches for all to service_role using (true) with check (true);

-- هل السرّ مسجّل ومؤكد؟ (يستخدمه save_search داخليًا — لا يُمنح لـ anon مباشرة)
create or replace function search_owner_exists(p_secret text)
returns boolean
language sql
security definer
stable
as $$
  select exists (select 1 from users where secret = p_secret and verified)
$$;

-- حفظ بحث: إدراج جديد، أو تحديث إن وُجد id مملوك لنفس السرّ
create or replace function save_search(
  p_secret text,
  p_name text,
  p_request text,
  p_transaction text,
  p_property text,
  p_areas text[],
  p_govs text[],
  p_min numeric,
  p_max numeric,
  p_id bigint default 0
) returns bigint
language plpgsql
security definer
as $$
declare
  v_id bigint;
begin
  if not search_owner_exists(p_secret) then
    raise exception 'invalid secret';
  end if;
  if p_id > 0 and exists (select 1 from saved_searches where id = p_id and user_secret = p_secret) then
    update saved_searches set
      name = p_name,
      request_text = p_request,
      transaction_type = p_transaction,
      property_type = p_property,
      areas = p_areas,
      governorates = p_govs,
      price_min = p_min,
      price_max = p_max
    where id = p_id and user_secret = p_secret
    returning id into v_id;
    return v_id;
  end if;
  insert into saved_searches (
    user_secret, name, request_text, transaction_type, property_type,
    areas, governorates, price_min, price_max
  ) values (
    p_secret, p_name, p_request, p_transaction, p_property,
    p_areas, p_govs, p_min, p_max
  )
  returning id into v_id;
  return v_id;
end;
$$;

-- قائمة أبحاث المستخدم (الأحدث أولًا) — بلا حقل السرّ نفسه؛ يرفض السرّ غير المسجّل
create or replace function list_saved_searches(p_secret text)
returns table (
  id bigint,
  name text,
  request_text text,
  transaction_type text,
  property_type text,
  areas text[],
  governorates text[],
  price_min numeric,
  price_max numeric,
  alert_enabled boolean,
  last_matched_at timestamptz,
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
    select s.id, s.name, s.request_text, s.transaction_type, s.property_type,
           s.areas, s.governorates, s.price_min, s.price_max,
           s.alert_enabled, s.last_matched_at, s.created_at
    from saved_searches s
    where s.user_secret = p_secret
    order by s.created_at desc;
end;
$$;

-- حذف بحث (فقط ما يملكه السرّ — يرفض السرّ غير المسجّل)
create or replace function delete_saved_search(p_secret text, p_id bigint)
returns boolean
language plpgsql
security definer
as $$
begin
  if not search_owner_exists(p_secret) then
    raise exception 'invalid secret';
  end if;
  delete from saved_searches where id = p_id and user_secret = p_secret;
  return found;
end;
$$;

-- تبديل التنبيه (نشط/متوقف) — فقط ما يملكه السرّ
create or replace function set_search_alert(p_secret text, p_id bigint, p_enabled boolean)
returns boolean
language plpgsql
security definer
as $$
begin
  if not search_owner_exists(p_secret) then
    raise exception 'invalid secret';
  end if;
  update saved_searches set alert_enabled = p_enabled
  where id = p_id and user_secret = p_secret;
  return found;
end;
$$;

revoke all on function search_owner_exists(text) from public;
revoke all on function save_search(text, text, text, text, text, text[], text[], numeric, numeric, bigint) from public;
revoke all on function list_saved_searches(text) from public;
revoke all on function delete_saved_search(text, bigint) from public;
revoke all on function set_search_alert(text, bigint, boolean) from public;

grant execute on function search_owner_exists(text) to service_role;
grant execute on function save_search(text, text, text, text, text, text[], text[], numeric, numeric, bigint) to anon, service_role;
grant execute on function list_saved_searches(text) to anon, service_role;
grant execute on function delete_saved_search(text, bigint) to anon, service_role;
grant execute on function set_search_alert(text, bigint, boolean) to anon, service_role;
