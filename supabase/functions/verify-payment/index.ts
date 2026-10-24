// POST { study_id, payment_id } → re-checks a payment with Whop and marks the study paid if it is.
// Backup for a slow/missed webhook: the founder page calls this with the `payment` query
// param Whop appends to the redirect URL. It never trusts the browser — Whop decides.
import { markPaid } from "../_shared/payments.ts";
import { adminDb, corsHeaders, json } from "../_shared/util.ts";
import { getPayment } from "../_shared/whop.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);

  try {
    const { study_id, payment_id } = await req.json();
    if (!study_id || !payment_id) return json({ error: "study_id and payment_id required" }, 400);

    const payment = await getPayment(payment_id);
    // Strict here: the payment must carry this study's id, otherwise anyone could
    // attach someone else's payment to their study.
    if (payment.studyId !== study_id) return json({ paid: false, reason: "payment is not for this study" }, 400);

    const result = await markPaid(adminDb(), study_id, payment);
    return json({ paid: result.ok, ...(result.ok ? {} : { reason: result.reason }) });
  } catch (e) {
    console.error("[verify-payment]", e);
    return json({ error: String(e) }, 500);
  }
});
