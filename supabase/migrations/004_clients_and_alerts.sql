-- العملاء المحتملون: قاعدة قابلة للتوسع من الواجهة ومرتبطة تلقائيًا بالفرص
create table if not exists client_leads (
  id bigint generated always as identity primary key,
  phone text not null unique,
  area text,
  type text,
  price numeric,
  note text,
  created_at timestamptz not null default now()
);

alter table client_leads enable row level security;

create policy "public read client_leads"
  on client_leads for select
  using (true);

create policy "service write client_leads"
  on client_leads for insert
  with check (true);

create policy "service update client_leads"
  on client_leads for update
  using (true);

-- عميل أولي: الرقم الذي طلبه المستخدم (يُربط بالفرص تلقائيًا عند اكتمال تفاصيله)
insert into client_leads (phone, area, type, price, note)
values ('01064955051', NULL, NULL, NULL, 'عميل جديد أُضيف من لوحة العملاء — ننتظر تفاصيل المنطقة والنوع والميزانية ليُربط بالفرص تلقائيًا.')
on conflict (phone) do nothing;
