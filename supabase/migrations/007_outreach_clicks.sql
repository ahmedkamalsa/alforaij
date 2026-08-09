-- تتبع نقرات التسويق: كل نقرة «نسخ ملخص» أو «إرسال واتساب» على فرصة/عميل تُسجَّل هنا،
-- وتُجمَّع عدادات التفاعل لكل عميل في تبويب الأداء.
-- سياسات RLS: القراءة والكتابة لدور service_role فقط (أرقام العملاء بيانات خاصة).

create table if not exists outreach_clicks (
  id bigint generated always as identity primary key,
  client_phone text not null default '',
  client_area text not null default '',
  client_type text not null default '',
  opportunity_code text not null default '',
  action text not null default 'copy',
  channel text not null default '',
  created_at timestamptz not null default now()
);

create index if not exists outreach_clicks_phone_idx on outreach_clicks (client_phone);
create index if not exists outreach_clicks_created_idx on outreach_clicks (created_at desc);
create index if not exists outreach_clicks_code_idx on outreach_clicks (opportunity_code);

alter table outreach_clicks enable row level security;

create policy "service read outreach_clicks"
  on outreach_clicks for select to service_role
  using (true);

create policy "service write outreach_clicks"
  on outreach_clicks for insert to service_role
  with check (true);

create policy "service update outreach_clicks"
  on outreach_clicks for update to service_role
  using (true);

create policy "service delete outreach_clicks"
  on outreach_clicks for delete to service_role
  using (true);
