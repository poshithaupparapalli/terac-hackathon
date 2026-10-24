# vera — deploy

static site. one html file, no build step.

## 1. put it online (2 min)

**vercel**
```bash
npm i -g vercel
cd vera-deploy
vercel --prod
```

**netlify** — drag the `vera-deploy` folder onto app.netlify.com/drop

**github pages** — push the folder, settings → pages → deploy from branch

it works immediately in demo mode (example study, nothing saved).

## 2. database (5 min)

1. supabase.com → new project
2. sql editor → paste `schema.sql` → run
3. settings → api → copy the project url and the **anon public** key
4. paste both into `config.js`, redeploy

the front end can now create draft studies and read them back.

## 3. whop

1. create the product and copy its checkout link into `config.js`
2. the checkout button appends `metadata[study_id]` and a redirect back to
   `#study/<id>`, so the webhook knows which study was paid

## 4. the part the browser must not do

the front end **never** marks a study paid — there is no update policy for
`anon`, so it cannot. your webhook handler does it with the **service role**
key (server side only, never in the browser):

```js
// POST /api/whop-webhook
const studyId = event.data.metadata.study_id;

// always verify with whop before trusting the payload
const res = await fetch(`https://api.whop.com/api/v2/payments/${event.data.id}`, {
  headers: { Authorization: `Bearer ${process.env.WHOP_API_KEY}` }
});
const payment = await res.json();
if (payment.status !== 'paid') return new Response('ignored', { status: 200 });

await fetch(`${SUPABASE_URL}/rest/v1/studies?study_id=eq.${studyId}`, {
  method: 'PATCH',
  headers: {
    apikey: SERVICE_ROLE_KEY,
    Authorization: `Bearer ${SERVICE_ROLE_KEY}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    status: 'paid',
    payment: { whop_id: payment.id, paid: true }
  })
});

// then trigger the agent
```

## 5. what the agent writes

the study page reads these fields and renders as soon as they appear —
it polls every 8 seconds, so the founder watches it fill in live.

| field | shown as |
|---|---|
| `status` | the five-step timeline |
| `plan.agent_pushback[]` | "what vera changed" (html allowed: `<s>` and `<b>`) |
| `plan.segments[] {name,count,why}` | "who's testing", with bars |
| `plan.questions[]` | question list (everything after the first is tagged "added by vera") |
| `plan.wtp_questions[]` | tagged "price" |
| `responses[]` | the live count |
| `report.themes[]` + `report.quotes[]` | paired theme cards |
| `report.price_range` | the range bar (needs two numbers, e.g. `"$29–$64"`) |
| `report.recommendation` | the box at the bottom |

the memo stays an empty state until `status` is `done`.

## pages

`#home` · `#brief` · `#pay` · `#studies` · `#study/<id>`

sign-up is email-only and kept in `localStorage` so "my studies" can find
them again. swap in supabase auth later if you need real accounts.
