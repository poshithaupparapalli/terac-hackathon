// Whop → payment.succeeded → verify signature → re-fetch payment from Whop → mark study paid → trigger agent.
// Deploy with --no-verify-jwt (Whop doesn't send a Supabase JWT).
import { markPaid } from "../_shared/payments.ts";
import { adminDb, json } from "../_shared/util.ts";
import { getPayment, verifyWebhook } from "../_shared/whop.ts";

Deno.serve(async (req) => {
  if (req.method !== "POST") return json({ error: "POST only" }, 405);

  const raw = await req.text();
  if (!(await verifyWebhook(req, raw))) {
    console.warn("[vera-webhook] bad signature");
    return json({ error: "invalid signature" }, 401);
  }

  const event = JSON.parse(raw);
  const webhookId = req.headers.get("webhook-id")!;
  const db = adminDb();
  const log = (outcome: string, extra: Record<string, unknown> = {}) =>
    db.from("whop_events").upsert({ webhook_id: webhookId, type: event.type, payload: event, outcome, ...extra });

  if (event.type !== "payment.succeeded") {
    await log("ignored");
    return json({ ok: true, ignored: event.type });
  }

  try {
    const payment = await getPayment(event.data?.id);
    let studyId = payment.studyId;

    // Fallback if metadata didn't come through: the most recent unpaid study with the payer's email.
    if (!studyId && payment.email) {
      const { data } = await db.from("studies").select("study_id")
        .eq("startup->>email", payment.email).eq("payment->>paid", "false")
        .order("created_at", { ascending: false }).limit(1).maybeSingle();
      studyId = data?.study_id ?? null;
    }
    if (!studyId) {
      await log("no_matching_study", { payment_id: payment.id });
      return json({ ok: true, warning: "no matching study" });
    }

    const result = await markPaid(db, studyId, payment);
    await log(result.ok ? (result.already ? "duplicate" : "marked_paid") : `rejected: ${result.reason}`,
      { payment_id: payment.id, study_id: studyId });
    return json({ ok: true, study_id: studyId, result: result.ok ? "paid" : result.reason });
  } catch (e) {
    console.error("[vera-webhook]", e);
    await log(`error: ${e}`);
    return json({ error: String(e) }, 500); // non-2xx → Whop retries
  }
});
