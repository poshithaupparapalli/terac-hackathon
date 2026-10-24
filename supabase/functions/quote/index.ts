// GET → the three tiers with the full price breakdown, for the intake form.
import { allTiers, OUR_FEE_PCT } from "../_shared/pricing.ts";
import { corsHeaders, json } from "../_shared/util.ts";

Deno.serve((req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  return json({
    our_fee_pct: OUR_FEE_PCT,
    note: "Terac cost is an estimate; testers are paid by Terac from the study budget.",
    tiers: allTiers(),
  });
});
