// deno test supabase/functions/_shared/pricing.test.ts
import { assertEquals } from "jsr:@std/assert@1";
import { quote, splitPayment } from "./pricing.ts";

Deno.test("fee split is 20/80 and sums to the amount paid", () => {
  assertEquals(splitPayment(25), { our_fee: 5, study_budget: 20 });
  const s = splitPayment(33.33);
  assertEquals(Math.round((s.our_fee + s.study_budget) * 100), 3333);
});

Deno.test("quote's study budget always covers the buffered Terac estimate", () => {
  for (const n of [1, 5, 15, 30, 100]) {
    const q = quote(n);
    const buffered = q.est_terac_cost_usd * (1 + q.buffer_pct);
    if (q.study_budget + 1e-9 < buffered) throw new Error(`${n} testers: budget ${q.study_budget} < ${buffered}`);
  }
});
