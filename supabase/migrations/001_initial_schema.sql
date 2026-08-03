create table if not exists listings (
  id bigserial primary key,
  code text unique,
  source text not null default 'alforaij',
  transaction_type text,
  governorate text,
  area text,
  property_type text,
  detail_class text,
  price numeric,
  price_text text,
  space numeric,
  listing_mode text,
  summary text,
  features text,
  published_date date,
  original_url text,
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists saved_reports (
  id bigserial primary key,
  request_text text not null,
  extracted_request jsonb not null,
  report jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists listings_area_idx on listings (area);
create index if not exists listings_type_idx on listings (property_type);
create index if not exists listings_transaction_idx on listings (transaction_type);
create index if not exists listings_price_idx on listings (price);
create index if not exists listings_space_idx on listings (space);
