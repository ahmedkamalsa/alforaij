-- 025_rls_fix_three_tables.sql
-- إصلاح 3 أخطاء RLS المعطلة (Security Advisor: RLS Disabled in public)
-- الجداول: client_request_messages / client_request_matches / listing_quality_events
-- النمط: ALTER TABLE ... ENABLE RLS + DROP/CREATE POLICY idempotent
-- يطبق عبر SQL Editor أو Management API — آمن لإعادة التشغيل

-- client_request_messages — رسائل المحادثة الخام (نص + media_storage_path)
alter table public.client_request_messages enable row level security;

drop policy if exists "client_request_messages_service_all" on public.client_request_messages;
create policy "client_request_messages_service_all" on public.client_request_messages
  for all to service_role
  using (true)
  with check (true);

drop policy if exists "client_request_messages_anon_read" on public.client_request_messages;
create policy "client_request_messages_anon_read" on public.client_request_messages
  for select to anon
  using (true);

-- client_request_matches — طبقة المطابقة القابلة للتدقيق (request_id → listing)
alter table public.client_request_matches enable row level security;

drop policy if exists "client_request_matches_service_all" on public.client_request_matches;
create policy "client_request_matches_service_all" on public.client_request_matches
  for all to service_role
  using (true)
  with check (true);

drop policy if exists "client_request_matches_anon_read" on public.client_request_matches;
create policy "client_request_matches_anon_read" on public.client_request_matches
  for select to anon
  using (true);

-- listing_quality_events — سجل قرارات جودة/مقياس السعر (audit trail)
alter table public.listing_quality_events enable row level security;

drop policy if exists "listing_quality_events_service_all" on public.listing_quality_events;
create policy "listing_quality_events_service_all" on public.listing_quality_events
  for all to service_role
  using (true)
  with check (true);

drop policy if exists "listing_quality_events_anon_read" on public.listing_quality_events;
create policy "listing_quality_events_anon_read" on public.listing_quality_events
  for select to anon
  using (true);
