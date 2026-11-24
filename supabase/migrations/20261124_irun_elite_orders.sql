-- HSW365 Elite website orders: intake after purchase -> demo build -> customer approval / revision.
create extension if not exists pgcrypto;
create table if not exists public.irun_elite_orders (
  id uuid primary key default gen_random_uuid(),
  key text not null default encode(gen_random_bytes(12), 'hex'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  status text not null default 'new',          -- new | building | demo_ready | revision | approved | failed
  order_ref text,
  name text not null,
  email text not null,
  phone text,
  business text not null,
  intake jsonb not null default '{}'::jsonb,
  version int not null default 0,
  demo_html text,
  demo_path text,
  revision_notes text,
  history jsonb not null default '[]'::jsonb,
  error text
);
create index if not exists irun_elite_orders_status_idx on public.irun_elite_orders (status, created_at);
alter table public.irun_elite_orders enable row level security;  -- no policies: service role only (edge function + engine)
