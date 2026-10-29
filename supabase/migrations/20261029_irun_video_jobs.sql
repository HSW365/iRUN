-- iRun Video: members upload a photo (+ song) + description; iRun renders a music video, short film or UGC ad.
create table if not exists public.irun_video_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  email text,
  app text not null default 'studio365',
  kind text not null check (kind in ('music_video','short_film','ugc')),
  title text check (length(title) <= 80),
  artist text check (length(artist) <= 80),
  description text not null check (length(description) between 10 and 2000),
  style text check (length(style) <= 40),
  length_s int not null default 60 check (length_s between 15 and 300),
  photo_path text not null,
  song_path text,
  status text not null default 'queued' check (status in ('queued','rendering','done','failed')),
  progress int not null default 0,
  stage text,
  video_url text,
  poster_url text,
  error text,
  report jsonb,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);
create index if not exists irun_video_jobs_user on public.irun_video_jobs(user_id, created_at desc);
create index if not exists irun_video_jobs_queue on public.irun_video_jobs(status, created_at);
alter table public.irun_video_jobs enable row level security;
drop policy if exists irun_video_jobs_own on public.irun_video_jobs;
create policy irun_video_jobs_own on public.irun_video_jobs for select to authenticated using (user_id = auth.uid());

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('irun-video', 'irun-video', false, 52428800,
        array['image/jpeg','image/png','image/webp','audio/mpeg','audio/mp3','audio/wav','audio/x-wav','audio/wave','audio/mp4','audio/x-m4a','audio/aac','audio/ogg','audio/flac'])
on conflict (id) do update set file_size_limit = excluded.file_size_limit, allowed_mime_types = excluded.allowed_mime_types;
