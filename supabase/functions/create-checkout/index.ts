// POST { study_id, tier } → { checkout_url }
// Frontend creates the study row (status draft), then calls this and redirects to checkout_url.
import { isTier, tierQuote } from "../_shared/pricing.ts";
import { adminDb, corsHeaders, json } from "../_shared/util.ts";
import { createCheckout } from "../_shared/whop.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);

  try {
    const { study_id, tier } = await req.json();
    if (!study_id) return json({ error: "study_id required" }, 400);
    if (!isTier(tier)) return json({ error: "tier must be starter | standard | pro" }, 400);

    const db = adminDb();
    const { data: study, error } = await db.from("studies").select("*").eq("study_id", study_id).single();
    if (error || !study) return json({ error: "study not found" }, 404);
    if (study.payment?.paid) return json({ error: "study already paid" }, 409);

    const planId = Deno.env.get(`WHOP_PLAN_${tier.toUpperCase()}`);
    if (!planId) return json({ error: `WHOP_PLAN_${tier.toUpperCase()} not configured` }, 500);

    const q = tierQuote(tier);
    const redirectTemplate = Deno.env.get("CHECKOUT_REDIRECT_URL"); // e.g. https://app.lovable.app/results/{study_id}
    const checkout = await createCheckout(planId, study_id, redirectTemplate?.replace("{study_id}", study_id));

    await db.from("studies").update({
      brief: { ...study.brief, budget_usd: q.price_usd, tier, tester_count: q.tester_count },
      payment: { ...study.payment, tier, quote: q, checkout_id: checkout.id },
    }).eq("study_id", study_id);

    return json({ study_id, checkout_url: checkout.url, quote: q });
  } catch (e) {
    console.error("[create-checkout]", e);
    return json({ error: String(e) }, 500);
  }
});
