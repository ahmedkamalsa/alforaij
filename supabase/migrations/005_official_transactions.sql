-- الصفقات الرسمية / التسجيل العقاري: أقوى مصدر لتقييم السعر عند توفره
create table if not exists official_transactions (
  id bigint generated always as identity primary key,
  reference text not null unique,
  area text not null,
  property_type text,
  transaction_type text not null default 'للبيع',
  price numeric,
  space numeric,
  date date,
  original_url text,
  source_note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists official_transactions_area_idx on official_transactions (area);
create index if not exists official_transactions_type_idx on official_transactions (property_type);
create index if not exists official_transactions_date_idx on official_transactions (date desc);

alter table official_transactions enable row level security;

create policy "public read official_transactions"
  on official_transactions for select
  using (true);

create policy "service write official_transactions"
  on official_transactions for insert to service_role
  with check (true);

create policy "service update official_transactions"
  on official_transactions for update to service_role
  using (true);

create policy "service delete official_transactions"
  on official_transactions for delete to service_role
  using (true);
