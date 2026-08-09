create table if not exists search_history (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  request_text text not null,
  transaction_type text,
  property_type text,
  areas text[] not null default '{}',
  governorates text[] not null default '{}',
  result_count integer not null default 0,
  top_code text,
  top_source text,
  top_area text,
  top_price numeric,
  top_recommendation numeric,
  top_data_quality jsonb not null default '{}'::jsonb,
  source_summary jsonb not null default '[]'::jsonb,
  report_summary text
);

create index if not exists search_history_created_at_idx
  on search_history (created_at desc);

create index if not exists search_history_area_idx
  on search_history using gin (areas);

alter table search_history enable row level security;

drop policy if exists "service write search history" on search_history;
create policy "service write search history"
  on search_history for insert to service_role
  with check (true);

drop policy if exists "service read search history" on search_history;
create policy "service read search history"
  on search_history for select to service_role
  using (true);
