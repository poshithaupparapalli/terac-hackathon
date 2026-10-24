-- Newer Supabase projects don't auto-grant table privileges to the API roles.
-- RLS policies still decide which rows; these only allow the roles to reach the tables at all.
grant usage on schema public to anon, authenticated, service_role;

grant select, insert on public.studies to anon, authenticated;   -- no update/delete: browser can't edit studies
grant all on public.studies to service_role;                     -- edge functions + agents
grant all on public.whop_events to service_role;
