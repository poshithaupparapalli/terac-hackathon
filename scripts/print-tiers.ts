// deno run scripts/print-tiers.ts
// Prints the tier prices to set on the 3 Whop plans. Re-run whenever the estimate changes.
import { allTiers } from "../supabase/functions/_shared/pricing.ts";

console.table(allTiers().map((t) => ({
  tier: t.name,
  testers: t.tester_count,
  "Whop price $": t.price_usd,
  "est Terac $": t.est_terac_cost_usd,
  "our 20% $": t.our_fee,
  "study budget $": t.study_budget,
  "cushion $": +(t.study_budget - t.est_terac_cost_usd).toFixed(2),
})));
