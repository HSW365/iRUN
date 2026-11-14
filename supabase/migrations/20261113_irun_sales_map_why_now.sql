-- Sales Agent: map pins and a "why now" line per prospect.
alter table public.irun_sales_leads add column if not exists why_now text;
alter table public.irun_sales_leads add column if not exists lat double precision;
alter table public.irun_sales_leads add column if not exists lon double precision;
alter table public.irun_sales_leads add column if not exists distance_mi real;
