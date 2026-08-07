-- الفرص اليومية والتوقعات: لقطة تُحدَّث أول بأول
create table if not exists opportunities (
  id bigint generated always as identity primary key,
  snapshot_date text not null unique,
  generated_at text,
  total_scored integer not null default 0,
  tiers jsonb not null default '{}'::jsonb,
  forecast jsonb not null default '[]'::jsonb,
  note text,
  created_at timestamptz not null default now()
);

alter table opportunities enable row level security;

create policy "public read opportunities"
  on opportunities for select
  using (true);

create policy "service write opportunities"
  on opportunities for insert
  with check (true);

create policy "service update opportunities"
  on opportunities for update
  using (true);
