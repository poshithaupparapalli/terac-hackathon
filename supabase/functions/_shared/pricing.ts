// Pricing model. Single source of truth for quotes, tier prices and fee math.
//
//   price = testers × est_terac_cost_per_tester × (1 + buffer) ÷ (1 − our_fee_pct)
//
// We keep OUR_FEE_PCT of whatever the founder actually pays; the rest is the
// study budget that funds Terac. The buffer exists because we do not yet know
// what Terac really charges — once Person 3 records the actual Terac cost we
// compare it to the estimate (see record_terac_cost in the migration).
//
// ⚠️ ESTIMATE_* values are placeholders until Terac staff confirm real pricing.
// If you change them, run `deno run scripts/print-tiers.ts` and update the
// three plan prices in Whop to match — Whop charges the plan price, not this.

export const OUR_FEE_PCT = 0.20;
export const ESTIMATE_TERAC_COST_PER_TESTER_USD = 4.00; // TODO: confirm with Terac
export const ESTIMATE_BUFFER_PCT = 0.25;
const ROUND_UP_TO_USD = 5;

export type TierId = "starter" | "standard" | "pro";

export const TIER_TESTERS: Record<TierId, number> = {
  starter: 5,
  standard: 15,
  pro: 30,
};

export const TIER_NAMES: Record<TierId, string> = {
  starter: "Starter",
  standard: "Standard",
  pro: "Pro",
};

const cents = (usd: number) => Math.round(usd * 100);
const usd = (c: number) => c / 100;

export function quote(testers: number) {
  const estTeracCents = cents(testers * ESTIMATE_TERAC_COST_PER_TESTER_USD);
  const bufferedCents = Math.round(estTeracCents * (1 + ESTIMATE_BUFFER_PCT));
  const rawPriceCents = Math.ceil(bufferedCents / (1 - OUR_FEE_PCT));
  const step = ROUND_UP_TO_USD * 100;
  const priceCents = Math.ceil(rawPriceCents / step) * step;
  const split = splitPayment(usd(priceCents));
  return {
    tester_count: testers,
    price_usd: usd(priceCents),
    est_terac_cost_usd: usd(estTeracCents),
    est_terac_cost_per_tester_usd: ESTIMATE_TERAC_COST_PER_TESTER_USD,
    buffer_pct: ESTIMATE_BUFFER_PCT,
    our_fee: split.our_fee,
    study_budget: split.study_budget,
  };
}

export function tierQuote(tier: TierId) {
  return { tier, name: TIER_NAMES[tier], ...quote(TIER_TESTERS[tier]) };
}

export function allTiers() {
  return (Object.keys(TIER_TESTERS) as TierId[]).map(tierQuote);
}

export function isTier(x: unknown): x is TierId {
  return typeof x === "string" && x in TIER_TESTERS;
}

// Fee math on what was ACTUALLY paid (from Whop), in cents to avoid float drift.
export function splitPayment(paidUsd: number) {
  const paid = cents(paidUsd);
  const fee = Math.round(paid * OUR_FEE_PCT);
  return { our_fee: usd(fee), study_budget: usd(paid - fee) };
}
