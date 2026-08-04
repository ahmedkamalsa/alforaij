create table if not exists source_registry (
  id text primary key,
  name text not null,
  category text not null,
  connection text not null,
  role text not null,
  trust_level text not null,
  scoring_policy text not null,
  evidence_policy text not null,
  status text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists source_runs (
  id bigserial primary key,
  source_id text references source_registry(id),
  request_text text,
  request_json jsonb not null default '{}'::jsonb,
  status text not null,
  records_found integer not null default 0,
  records_scored integer not null default 0,
  response_ms numeric,
  source_url text,
  note text,
  error text,
  started_at timestamptz not null default now()
);

create table if not exists listing_evidence (
  id bigserial primary key,
  listing_code text not null,
  source_id text references source_registry(id),
  evidence_type text not null,
  evidence_url text,
  field_name text,
  field_value text,
  confidence numeric,
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists source_runs_source_idx on source_runs (source_id);
create index if not exists source_runs_started_idx on source_runs (started_at desc);
create index if not exists listing_evidence_code_idx on listing_evidence (listing_code);
create index if not exists listing_evidence_source_idx on listing_evidence (source_id);
