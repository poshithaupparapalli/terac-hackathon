-- vera — run this in supabase → sql editor

create extension if not exists "pgcrypto";

create table if not exists studies (
  study_id   uuid primary key default gen_random_uuid(),
  status     text not null default 'draft'
             check (status in ('draft','paid','live','collecting','done')),
  startup    jsonb not null default '{}'::jsonb,
  brief      jsonb not null default '{}'::jsonb,
  plan       jsonb not null default '{"segments":[],"agent_pushback":[],"questions":[],"wtp_questions":[]}'::jsonb,
  payment    jsonb not null default '{"whop_id":"","paid":false,"our_fee":0,"study_budget":0}'::jsonb,
  terac      jsonb not null default '{"study_ref":"","posted_at":null}'::jsonb,
  responses  jsonb not null default '[]'::jsonb,
  report     jsonb not null default '{"themes":[],"quotes":[],"price_range":"","recommendation":""}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists studies_email_idx
  on studies ((startup->>'email'));

alter table studies enable row level security;

-- the front end only ever creates a draft and reads studies.
-- everything after payment is written by your server / webhook
-- using the service role key, which bypasses these policies.

create policy "anyone can create a draft study"
  on studies for insert to anon
  with check (status = 'draft');

create policy "anyone with the study id can read it"
  on studies for select to anon
  using (true);

-- deliberately no update/delete policy for anon:
-- a browser can never mark a study paid.
