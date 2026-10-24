# Backend (Person 1): money + plumbing

Supabase (Postgres + Edge Functions) + Whop. Lovable connects to the same Supabase project.

## ✅ Live now (start here)

| | |
|---|---|
| Supabase project | `lcsjutaaxzntwxfgvhjj` → `https://lcsjutaaxzntwxfgvhjj.supabase.co` |
| Keys | Frontend: the **`terac` publishable key** (`sb_publishable_…`). Backend/agents: the **`terac` secret key** (`sb_secret_…`, never in browser code). Both are under Project Settings → API Keys. Legacy `eyJ…` keys are being retired, so don't use them. |
| Functions | `quote`, `create-checkout`, `verify-payment`, `vera-webhook` (all deployed) |
| Whop (LIVE, real money) | product `prod_GcqIbs2eO7Zpu`: Starter `plan_lrynah65qG2MQ` $35, Standard `plan_nN6qQxUXLOO6i` $95, Pro `plan_VKmRditVebIwg` $190 |
| Tested | create study → `create-checkout` → real Whop checkout carrying the study id; webhook signature verified with Whop test events |
| Not yet tested | a real payment flipping `paid:true`. That happens with the first real customer. |

**Still needed from teammates:**
- Person 4: founder-page URL, which becomes `CHECKOUT_REDIRECT_URL`. Until it's set, Whop shows its own confirmation page.
- Person 2: planner URL, which becomes `AGENT_TRIGGER_URL`. Or poll for `status='paid'`.
- Person 3: call `record_terac_cost` once Terac shows the real cost. The $4/tester figure is a guess.

The setup checklist further down is already done. It's kept for reference.

```
Intake form ──insert──▶ studies (status=draft)
     │
     └─POST create-checkout {study_id, tier} ──▶ Whop checkout (tier's fixed plan, metadata.study_id)
                                                   │ founder pays
Whop ──payment.succeeded──▶ vera-webhook ──verify signature──▶ GET payment from Whop (must be "paid")
                                │
                                └─▶ studies.payment = {paid:true, our_fee 20%, study_budget 80%}, status=paid
                                    └─▶ POST AGENT_TRIGGER_URL {study_id}   (Person 2 plans → Person 3 posts to Terac)
```

## Pricing (an estimate, because we don't know Terac's real cost yet)

`price = testers × est_terac_cost_per_tester × (1 + 25% buffer) ÷ 0.8`, rounded up to $5.
We keep 20% of what's **actually paid**, and the other 80% is the study budget that funds Terac. Terac pays the testers.

| Tier | Testers | Whop price | Est. Terac cost | Our 20% | Study budget |
|---|---|---|---|---|---|
| Starter | 5 | **$35** | $20 | $7 | $28 |
| Standard | 15 | **$95** | $60 | $19 | $76 |
| Pro | 30 | **$190** | $120 | $38 | $152 |

These prices assume **$4/tester**, which is a placeholder. Edit `ESTIMATE_*` in [pricing.ts](supabase/functions/_shared/pricing.ts) once Terac answers, then run `deno run scripts/print-tiers.ts` and update the 3 Whop plan prices to match.
Once Terac shows the real cost, Person 3 calls `record_terac_cost`, which stores the actual cost, the surplus vs. budget, and the actual-vs-estimate %.

## Data: `studies` table = the shared object

`select * from studies where study_id = …` returns the shared JSON object exactly
(`study_id, status, startup, brief, plan, payment, terac, responses, report`).
**Fields added, none renamed:** `brief.tier`, `brief.tester_count`, and in `payment`: `tier, quote, checkout_id, paid_usd, paid_at, terac_actual_cost, terac_variance`.

## API for each teammate

**Person 4 (Lovable / frontend)**, using the anon key:
1. Get the tiers for the form: `supabase.functions.invoke('quote')` → `{ tiers: [{tier, name, tester_count, price_usd, our_fee, study_budget, est_terac_cost_usd}] }`
2. Create the study: `supabase.from('studies').insert({ startup:{name,email,mission,founders,product_url}, brief:{feedback_goals,persona,budget_usd:0} }).select().single()`
3. Pay: `supabase.functions.invoke('create-checkout', { body:{ study_id, tier } })` → redirect to `checkout_url`
4. Founder page `/results/{study_id}` (Whop redirects here with `?payment=…&status=…`):
   - If `payment` is in the URL: `invoke('verify-payment', { body:{ study_id, payment_id } })`. This is a backup in case the webhook is slow.
   - Read the row, and subscribe to realtime on `studies` for live status changes.
5. Tester page `/study/{id}`: read the row for instructions and `startup.product_url`, then submit with
   `supabase.rpc('submit_response', { p_study_id, p_tester_id, p_segment, p_answers })`.
   This works only when the status is `paid | live | collecting`, and it moves `live → collecting`.
The frontend **cannot update** studies (RLS). That is deliberate, so nobody can set `paid:true` from the browser.

**Person 2 (planner)**, using the service-role key (ask Person 1):
- Get triggered: give Person 1 an HTTPS URL. It receives `POST {study_id, event:"study.paid"}` with the header `x-trigger-secret`.
  Without a URL, poll for `status = 'paid'` and `plan->segments` being empty.
- Write the plan: `update studies set plan = {...} where study_id = …`. Use `brief.tester_count` for the segment counts.

**Person 3 (Terac + results)**, using the service-role key:
- After posting: `terac = {study_ref, posted_at}`, `status = 'live'`
- Real cost from Terac: `supabase.rpc('record_terac_cost', { p_study_id, p_cost_usd })`
- Write the report: `report = {...}`, `status = 'done'`

## Setup checklist (Person 1)

### Supabase
1. Create a project at supabase.com. **Invite Person 4 to the org** so Lovable can connect to this project. Lovable shouldn't make its own.
2. SQL Editor → paste and run [the migration](supabase/migrations/20261024160000_init.sql).
3. Share the project URL and anon key with everyone. Share the service-role key only with Persons 2 and 3.

### Whop, in sandbox first (sandbox.whop.com, test card `4242 4242 4242 4242`)
4. Create the business, then one product ("AI User Research Study") with 3 one-time plans: $35 / $95 / $190. Copy each `plan_…` id.
5. Developer → Account API Keys → create a key (Admin role).
6. Deploy the functions (below). Then Developer → Webhooks → Create webhook:
   URL `https://<project-ref>.supabase.co/functions/v1/vera-webhook`, API version `v1`, event `payment.succeeded`. Copy the `ws_…` secret.
7. Fill in `supabase/.env` from [.env.example](supabase/.env.example), then `supabase secrets set --env-file supabase/.env`.
8. Test the whole flow with the test card, and check `whop_events.outcome = 'marked_paid'`.
9. **Go live:** repeat steps 4–6 on whop.com, update the secrets, and remove `WHOP_API_BASE`.

### Deploy
```
brew install supabase/tap/supabase deno
supabase login && supabase link --project-ref <ref>
supabase functions deploy quote create-checkout verify-payment
supabase functions deploy vera-webhook --no-verify-jwt
```

## Debugging
- `select webhook_id, type, outcome, payment_id, study_id, received_at from whop_events order by received_at desc;`
- Function logs: Supabase dashboard → Edge Functions → *function* → Logs.
- If `create-checkout` returns a Whop error, the response body is logged. A field name in the Whop API may differ (`purchase_url`), so check the logs first.
