-- 024_ai_agents_audit.sql
-- Audit trail for AI providers, analysis agents, partner feeds, and data quality.

create table if not exists public.ai_provider_runs (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  request_text text not null default '',
  provider text not null,
  model text not null default '',
  status text not null,
  response_ms numeric,
  error text,
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.analysis_agent_runs (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  request_text text not null default '',
  agent_id text not null,
  agent_name text not null,
  status text not null,
  summary text not null default '',
  outputs jsonb not null default '{}'::jsonb
);

create table if not exists public.analysis_agent_steps (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  request_text text not null default '',
  agent_id text not null,
  step_key text not null,
  step_value jsonb not null default '{}'::jsonb
);

create table if not exists public.partner_feeds (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  source_id text references public.source_registry(id),
  source_name text not null,
  access_model text not null default 'partner_required',
  status text not null default 'planned',
  endpoint_url text,
  contract_note text,
  last_checked_at timestamptz,
  metadata jsonb not null default '{}'::jsonb
);

create table if not exists public.data_quality_events (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  request_text text not null default '',
  source_id text references public.source_registry(id),
  listing_code text,
  event_type text not null,
  severity text not null default 'info',
  reason text not null default '',
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists ai_provider_runs_created_idx on public.ai_provider_runs (created_at desc);
create index if not exists ai_provider_runs_provider_idx on public.ai_provider_runs (provider, status);
create index if not exists analysis_agent_runs_created_idx on public.analysis_agent_runs (created_at desc);
create index if not exists analysis_agent_runs_agent_idx on public.analysis_agent_runs (agent_id, status);
create index if not exists analysis_agent_steps_agent_idx on public.analysis_agent_steps (agent_id, created_at desc);
create index if not exists partner_feeds_source_idx on public.partner_feeds (source_id, status);
create index if not exists data_quality_events_source_idx on public.data_quality_events (source_id, severity);
create index if not exists data_quality_events_listing_idx on public.data_quality_events (listing_code);

alter table public.ai_provider_runs enable row level security;
alter table public.analysis_agent_runs enable row level security;
alter table public.analysis_agent_steps enable row level security;
alter table public.partner_feeds enable row level security;
alter table public.data_quality_events enable row level security;

create policy "ai_provider_runs_service_all" on public.ai_provider_runs
  for all to service_role
  using (true)
  with check (true);

create policy "analysis_agent_runs_service_all" on public.analysis_agent_runs
  for all to service_role
  using (true)
  with check (true);

create policy "analysis_agent_steps_service_all" on public.analysis_agent_steps
  for all to service_role
  using (true)
  with check (true);

create policy "partner_feeds_service_all" on public.partner_feeds
  for all to service_role
  using (true)
  with check (true);

create policy "data_quality_events_service_all" on public.data_quality_events
  for all to service_role
  using (true)
  with check (true);
