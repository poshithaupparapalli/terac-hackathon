import type { SupabaseClient } from "jsr:@supabase/supabase-js@2";
import { splitPayment } from "./pricing.ts";
import type { getPayment } from "./whop.ts";

type VerifiedPayment = Awaited<ReturnType<typeof getPayment>>;

// Marks a study paid from a payment that was re-fetched from Whop.
// Idempotent: a second call for an already-paid study is a no-op.
export async function markPaid(db: SupabaseClient, studyId: string, p: VerifiedPayment) {
  if (!p.paid) return { ok: false, reason: `Whop says payment status is ${p.status}` };

  const { data: study, error } = await db.from("studies").select("*").eq("study_id", studyId).single();
  if (error || !study) return { ok: false, reason: "study not found" };
  if (study.payment?.paid) return { ok: true, already: true, study };

  // Fee math uses what Whop actually charged, not what we quoted.
  const paidUsd = p.amountUsd ?? Number(study.brief?.budget_usd ?? 0);
  const payment = {
    ...study.payment,
    whop_id: p.id,
    paid: true,
    paid_usd: paidUsd,
    paid_at: new Date().toISOString(),
    ...splitPayment(paidUsd),
  };

  const { data: updated, error: upErr } = await db
    .from("studies")
    .update({ payment, status: study.status === "draft" ? "paid" : study.status })
    .eq("study_id", studyId)
    .eq("payment->>paid", "false") // guards against two deliveries racing
    .select()
    .maybeSingle();
  if (upErr) return { ok: false, reason: upErr.message };
  if (!updated) return { ok: true, already: true, study };

  triggerAgent(studyId);
  return { ok: true, study: updated };
}

// Tells Person 2's planner that a paid study is ready. Fire-and-forget so the
// webhook can answer Whop within its 5 s limit.
function triggerAgent(studyId: string) {
  const url = Deno.env.get("AGENT_TRIGGER_URL");
  if (!url) {
    console.log(`[agent] AGENT_TRIGGER_URL not set; study ${studyId} is paid and waiting (agents can poll status='paid')`);
    return;
  }
  const task = fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-trigger-secret": Deno.env.get("AGENT_TRIGGER_SECRET") ?? "" },
    body: JSON.stringify({ study_id: studyId, event: "study.paid" }),
  })
    .then((r) => console.log(`[agent] trigger ${studyId} → ${r.status}`))
    .catch((e) => console.error(`[agent] trigger ${studyId} failed`, e));
  // deno-lint-ignore no-explicit-any
  (globalThis as any).EdgeRuntime?.waitUntil?.(task);
}
