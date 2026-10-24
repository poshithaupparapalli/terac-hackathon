-- One row per study. Columns mirror the team's shared data object exactly, so
-- `select * from studies` returns that object. Do not rename without telling the team.
--
-- Additive fields (not in the original object, flagged to the team):
--   brief.tier, brief.tester_count
--   payment.tier, payment.quote, payment.checkout_id, payment.paid_usd, payment.paid_at,
--   payment.terac_actual_cost, payment.terac_variance
create extension if not exists pgcrypto;

create table public.studies (
  study_id   uuid primary key default gen_random_uuid(),
  status     text not null default 'draft'
             check (status in ('draft', 'paid', 'live', 'collecting', 'done')),
  startup    jsonb not null default '{"name":"","email":"","mission":"","founders":"","product_url":""}',
  brief      jsonb not null default '{"feedback_goals":"","persona":"","budget_usd":0}',
  plan       jsonb not null default '{"segments":[],"agent_pushback":[],"questions":[],"wtp_questions":[]}',
  payment    jsonb not null default '{"whop_id":"","paid":false,"our_fee":0,"study_budget":0}',
  terac      jsonb not null default '{"study_ref":"","posted_at":""}',
  responses  jsonb not null default '[]',
  report     jsonb not null default '{"themes":[],"quotes":[],"price_range":"","recommendation":""}',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Every Whop webhook delivery, keyed by webhook-id for idempotency (Whop delivers at least once).
create table public.whop_events (
  webhook_id  text primary key,
  type        text not null,
  payment_id  text,
  study_id    uuid references public.studies(study_id),
  outcome     text,
  payload     jsonb not null,
  received_at timestamptz not null default now()
);

create or replace function public.touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

create trigger studies_touch before update on public.studies
for each row execute function public.touch_updated_at();

-- The public (anon) key can create a study, but it cannot create one that is
-- already paid or has a fake plan/report. Only the service role (our edge
-- functions + the agents) can set these columns.
create or replace function public.sanitize_new_study() returns trigger language plpgsql as $$
begin
  if coalesce(auth.role(), 'anon') <> 'service_role' then
    new.status    := 'draft';
    new.plan      := '{"segments":[],"agent_pushback":[],"questions":[],"wtp_questions":[]}';
    new.payment   := '{"whop_id":"","paid":false,"our_fee":0,"study_budget":0}';
    new.terac     := '{"study_ref":"","posted_at":""}';
    new.responses := '[]';
    new.report    := '{"themes":[],"quotes":[],"price_range":"","recommendation":""}';
  end if;
  return new;
end $$;

create trigger studies_sanitize before insert on public.studies
for each row execute function public.sanitize_new_study();

alter table public.studies enable row level security;
alter table public.whop_events enable row level security; -- no policies: service role only

-- No accounts today: anyone holding the study link (an unguessable uuid) can read it.
create policy "read studies" on public.studies for select to anon, authenticated using (true);
create policy "create studies" on public.studies for insert to anon, authenticated with check (true);
-- No update/delete policy → the frontend cannot edit a study; edge functions and agents use the service role.

-- Tester page submits through this. It appends atomically so concurrent testers don't overwrite each other.
create or replace function public.submit_response(
  p_study_id uuid, p_tester_id text, p_segment text, p_answers jsonb
) returns void language plpgsql security definer set search_path = public as $$
declare s text;
begin
  select status into s from studies where study_id = p_study_id for update;
  if s is null then raise exception 'study not found'; end if;
  if s not in ('paid', 'live', 'collecting') then raise exception 'study is not accepting responses (status %)', s; end if;
  update studies set
    responses = responses || jsonb_build_array(jsonb_build_object(
      'tester_id', coalesce(p_tester_id, ''), 'segment', coalesce(p_segment, ''), 'answers', coalesce(p_answers, '{}'::jsonb),
      'submitted_at', now())),
    status = case when s = 'live' then 'collecting' else s end
  where study_id = p_study_id;
end $$;

revoke all on function public.submit_response(uuid, text, text, jsonb) from public;
grant execute on function public.submit_response(uuid, text, text, jsonb) to anon, authenticated;

-- Person 3 calls this once Terac shows what the study really cost.
-- Records the actual cost and how it compares with the 80% study budget we collected.
create or replace function public.record_terac_cost(p_study_id uuid, p_cost_usd numeric)
returns jsonb language plpgsql security definer set search_path = public as $$
declare budget numeric; result jsonb;
begin
  select (payment->>'study_budget')::numeric into budget from studies where study_id = p_study_id;
  if budget is null then raise exception 'study not found'; end if;
  update studies set payment = payment || jsonb_build_object(
    'terac_actual_cost', p_cost_usd,
    'terac_variance', jsonb_build_object(
      'study_budget', budget,
      'surplus', round(budget - p_cost_usd, 2),          -- positive = estimate was high enough
      'actual_vs_estimate_pct', case when (payment->'quote'->>'est_terac_cost_usd')::numeric > 0
        then round(100 * p_cost_usd / (payment->'quote'->>'est_terac_cost_usd')::numeric, 1) end))
  where study_id = p_study_id
  returning payment into result;
  return result;
end $$;

revoke all on function public.record_terac_cost(uuid, numeric) from public, anon, authenticated;
grant execute on function public.record_terac_cost(uuid, numeric) to service_role;

-- Live updates on the founder page (status → paid → live → done).
alter publication supabase_realtime add table public.studies;
