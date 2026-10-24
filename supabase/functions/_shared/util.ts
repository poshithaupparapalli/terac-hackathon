import { createClient } from "jsr:@supabase/supabase-js@2";

export const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

export function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

export function env(name: string): string {
  const v = Deno.env.get(name);
  if (!v) throw new Error(`Missing env var ${name}`);
  return v;
}

// Service-role client: bypasses RLS. Only ever used server-side.
// VERA_SECRET_KEY is a new-style sb_secret_ key (survives disabling the legacy JWT keys).
export function adminDb() {
  const key = Deno.env.get("VERA_SECRET_KEY") ?? env("SUPABASE_SERVICE_ROLE_KEY");
  return createClient(env("SUPABASE_URL"), key, {
    auth: { persistSession: false },
  });
}
