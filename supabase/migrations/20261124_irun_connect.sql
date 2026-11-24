-- iRun Connect: the integrations hub (connect.html + edge function irun-connect).
-- Credentials stay server side: RLS on, no policies, so only the service role (edge function + engine) can read them.
create table if not exists public.irun_integrations (
  id text primary key,                                  -- discord, telegram, slack, canva, figma, shopify, ...
  creds jsonb not null default '{}'::jsonb,             -- keys / tokens (never returned to the browser)
  meta jsonb not null default '{}'::jsonb,              -- account label, chosen list, OAuth state, sync cursors
  auto_share boolean not null default false,            -- fan every new iRun post out to this channel
  lead_alerts boolean not null default false,           -- send new leads to this channel
  status text not null default 'connected',             -- connected | error | pending
  last_error text,
  connected_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.irun_integrations enable row level security;

-- Media brought into iRun from Canva, Figma, Spotify, Shopify, uploads: one list the hub can post, share or save from.
create table if not exists public.irun_library (
  id bigint generated always as identity primary key,
  created_at timestamptz not null default now(),
  source text not null,                                 -- canva | figma | spotify | shopify | upload | irun
  kind text not null,                                   -- image | video
  title text,
  url text not null,                                    -- public URL (irun-connect bucket or the source CDN)
  ref text,                                             -- id at the source (design id, frame id, track id)
  meta jsonb not null default '{}'::jsonb,
  posted jsonb not null default '[]'::jsonb             -- where it was posted / shared, with ids
);
create index if not exists irun_library_created_idx on public.irun_library (created_at desc);
alter table public.irun_library enable row level security;

-- Public bucket for hub media. irun-media only takes mp4; Instagram image posts need JPEG.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('irun-connect', 'irun-connect', true, 104857600, array['image/jpeg','image/png','image/webp','video/mp4'])
on conflict (id) do nothing;
