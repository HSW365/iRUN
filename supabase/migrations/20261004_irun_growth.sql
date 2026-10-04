-- iRun growth engine: plan/test fields and measured results on posts, plus Shopify orders.
alter table public.irun_posts
  add column if not exists angle text,
  add column if not exists format text not null default 'video',
  add column if not exists experiment text,
  add column if not exists variant text,
  add column if not exists media jsonb,
  add column if not exists metrics jsonb,
  add column if not exists score numeric,
  add column if not exists metrics_at timestamptz;

create index if not exists irun_posts_experiment_idx on public.irun_posts (experiment) where experiment is not null;

create table if not exists public.irun_orders (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  account text not null,
  shop_domain text,
  order_id text not null,
  name text,
  total numeric,
  currency text,
  item_count integer,
  items jsonb,
  landing_site text,
  referring_site text,
  placed_at timestamptz,
  unique (account, order_id)
);
-- Service role only (edge function + engine). No policies on purpose: nothing is readable with the public key.
alter table public.irun_orders enable row level security;
