-- iRun Fundraise: deck review, investor matching with scores, outreach to approved matches, meetings pipeline.
-- All tables are service-role only (the irun-client function checks the company's client key).

create table if not exists public.irun_fund_campaigns (
  company_id text primary key references public.irun_companies(id) on delete cascade,
  startup text,
  one_liner text,
  stage text check (stage in ('pre-seed','seed','series-a','series-b','growth')),
  raise_usd bigint check (raise_usd is null or raise_usd >= 0),
  check_usd bigint check (check_usd is null or check_usd >= 0),
  sectors text[] not null default '{}',
  geo text,
  traction text,
  booking_url text,
  deck_text text,
  send_enabled boolean not null default false,
  review_status text not null default 'none' check (review_status in ('none','requested','done','failed')),
  review jsonb,
  review_at timestamptz,
  review_error text,
  match_hash text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.irun_investors (
  id bigint generated always as identity primary key,
  company_id text not null references public.irun_companies(id) on delete cascade,
  name text not null,
  firm text,
  role text,
  type text not null default 'vc' check (type in ('vc','angel','family_office','accelerator','corporate','other')),
  email text,
  location text,
  stages text[] not null default '{}',
  sectors text[] not null default '{}',
  check_min bigint,
  check_max bigint,
  website text,
  note text,
  created_at timestamptz not null default now()
);
create unique index if not exists irun_investors_email on public.irun_investors(company_id, lower(email)) where email is not null;
create index if not exists irun_investors_company on public.irun_investors(company_id);

create table if not exists public.irun_fund_matches (
  id bigint generated always as identity primary key,
  company_id text not null references public.irun_companies(id) on delete cascade,
  investor_id bigint not null references public.irun_investors(id) on delete cascade,
  score int not null default 0 check (score between 0 and 100),
  reasons jsonb not null default '[]'::jsonb,
  status text not null default 'matched' check (status in
    ('matched','drafted','approved','sent','followed_up','replied','meeting','passed','bounced','unsubscribed')),
  subject text,
  body text,
  sends int not null default 0,
  last_sent_at timestamptz,
  replied_at timestamptz,
  meeting_at timestamptz,
  meeting_note text,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (company_id, investor_id)
);
create index if not exists irun_fund_matches_company on public.irun_fund_matches(company_id, status, score desc);

alter table public.irun_fund_campaigns enable row level security;
alter table public.irun_investors enable row level security;
alter table public.irun_fund_matches enable row level security;
