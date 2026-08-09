-- Hardening for public tables created by earlier/manual setup.
-- The backend uses SUPABASE_SERVICE_ROLE_KEY, so browser clients should not
-- read/write these tables directly. This migration is idempotent and skips
-- tables that do not exist in the current project.

do $$
declare
  target_table text;
  relation_type text;
  tables text[] := array[
    'market_data_operational_v1',
    'user_valuation_requests',
    'official_market_indicators',
    'market_ads',
    'pending_updates',
    'client_property_requests',
    'client_requests',
    'listing_quality',
    'listing_evidence',
    'source_runs',
    'source_registry',
    'saved_reports',
    'listings'
  ];
begin
  foreach target_table in array tables loop
    select table_type into relation_type
    from information_schema.tables
    where table_schema = 'public'
      and information_schema.tables.table_name = target_table;

    if relation_type = 'VIEW' then
      begin
        execute format('alter view public.%I set (security_invoker = true)', target_table);
      exception
        when others then
          raise notice 'Could not set security_invoker for view public.%: %', target_table, sqlerrm;
      end;
    elsif relation_type = 'BASE TABLE' then
      execute format('alter table public.%I enable row level security', target_table);

      execute format('drop policy if exists "service read %s" on public.%I', target_table, target_table);
      execute format('drop policy if exists "service write %s" on public.%I', target_table, target_table);
      execute format('drop policy if exists "service update %s" on public.%I', target_table, target_table);
      execute format('drop policy if exists "service delete %s" on public.%I', target_table, target_table);

      execute format('create policy "service read %s" on public.%I for select to service_role using (true)', target_table, target_table);
      execute format('create policy "service write %s" on public.%I for insert to service_role with check (true)', target_table, target_table);
      execute format('create policy "service update %s" on public.%I for update to service_role using (true) with check (true)', target_table, target_table);
      execute format('create policy "service delete %s" on public.%I for delete to service_role using (true)', target_table, target_table);
    end if;
  end loop;
end $$;
