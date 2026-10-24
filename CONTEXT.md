# Project Context (paste this into Claude before asking for help)

## Who we are and where
- Team of 4 at the **Terac Zero Human Company Hackathon**, NYC, Saturday Oct 24, 2026
- **Submissions lock at 6:45 PM.** Time is the main constraint. Prefer simple, working solutions over clever ones.
- We pivoted at ~3:30 PM from a previous idea. Build only what is described here.

## Hackathon rules we must meet
- Build one or more AI agents that **run a company autonomously** (little to no human involvement).
- **Terac MCP integration is mandatory.** Terac is "the expert labor MCP": an agent can source verified humans on demand, run studies, and get structured results back. Terac recruits, screens, verifies, and pays the humans itself.
- We must collect **real human input through Terac during the hackathon** and show it **measurably improved** the project (a before/after).
- The company must be **built on Whop**, and **all payments must go through Whop**. Whop is a commerce platform (products, checkout, payments, memberships) with an API, CLI, and MCP server. Its CLI has no sandbox: actions are real.
- **Any revenue we report must be real and organic.** Never fake orders, payments, or completed actions.
- Other sponsors we may use: **Lovable** (generates web apps from prompts), **Exa** (web search API for agents).

## What we are building (one line)
An autonomous agent company that runs user research for startups: a founder describes their product and what feedback they need, pays through Whop, and our agent designs the test group, recruits the right real testers through Terac, collects their feedback, and delivers a synthesized report, including willingness to pay.

## The problem
Early and late stage startups need real users to test their product, give feedback, and reveal willingness to pay. Finding the right testers who actually spend time on it is hard, and most founders don't know how to design good research (who to test with, what to ask, how to measure price).

## Why we are not just "a wrapper on Terac"
Terac already offers customer feedback studies. Our value is the layer on top:
1. **Judgment layer:** the agent turns a messy founder brief into a well-designed, diverse, unbiased test group, and pushes back when the founder's persona is too narrow or wrong.
2. **Research design:** the agent writes good questions, including ones the founder forgot.
3. **Willingness to pay:** built-in Van Westendorp price questions (too cheap to trust, a bargain, getting expensive, too expensive to consider).
4. **Synthesis:** a clear report with themes, quotes, an acceptable price range, and a recommendation, not raw responses.

Pitch line: "Founders don't know how to run user research. Our agent does it for them, end to end."

## End-to-end flow
1. **Startup intake (web form):** company name, email, mission, founders, product URL (live link; repo-to-Vercel deploy is cut for today), feedback goals (specific or general), target persona, budget.
2. **Payment:** startup pays the budget through **Whop checkout**.
3. **Whop webhook** confirms payment, sets the study to `paid`, and triggers the agent. The agent must verify payment with Whop, never trust a user saying "I paid."
4. **Agent plans the study:**
   - reads the brief
   - writes pushback on the brief (e.g. "you said biologists, but your buyer is a lab manager; include both")
   - designs segments with counts, reasons, and screener questions, with diversity across experience level, company size, region, etc.
   - writes feedback questions plus WTP questions
5. **Agent posts the study to Terac** via the Terac MCP.
6. **Testers** recruited by Terac are sent to our tester page `/study/{id}`, which shows instructions and the product link and collects their answers. No tester accounts today.
7. **Agent synthesizes** responses into a report.
8. **Founder views** the plan, the agent's reasoning, and the final report on their study page. No startup accounts today (study ID or link is fine).

## Money flow
- Startup pays $X on Whop. That is our real revenue (tracked by our **Whop Business ID**).
- Long-term model: we keep **20%**, and 80% funds the Terac study.
- **Today:** studies are funded by the **$100 in Terac event credits** (shared by the whole team). Testers are paid by **Terac**, not by us through Whop. Say this honestly in the demo.
- Terac sets the actual price per participant via a quote. $100 total limits how many testers we can run across all studies.

## Terac facts (from organizers + terac-cookbook repo)
- Credits: https://terac.com/r/ghdU4NpIZ9raQFxAFs39hH63yXl8iAV2 (no call or company email needed)
- Starter repo: https://github.com/TeracAI/terac-cookbook (Python, `uv`, "oracle" recipe, replay mode to test without spending)
- **Target the general population** for fastest results. Experts review studies, so results are not instant. Launch early.
- A study has: title, description, business_type (b2b/b2c), num_participants, audience filters (country filter required), device_types, tasks, and a quote (task/panel description, count, timeline hours, minutes per participant).
- A task of type `interview` with `auto_approve` needs an HTTPS `task_url`: our tester page. That page must implement Terac's completion callback.
- Launch is a separate, confirmed step after the quote and draft.

## Submission requirements (form opens 5:30, locks 6:45)
- Public GitHub repo
- 2-minute demo video
- Live deployment link
- Whop Business ID (`biz_...` from the whop.com/dashboard URL)

## Shared data object (everyone builds against this)
```json
{
  "study_id": "",
  "status": "draft | paid | live | collecting | done",
  "startup": {"name": "", "email": "", "mission": "", "founders": "", "product_url": ""},
  "brief": {"feedback_goals": "", "persona": "", "budget_usd": 0},
  "plan": {
    "segments": [{"name": "", "count": 0, "why": "", "screener": [""]}],
    "agent_pushback": [""],
    "questions": [""],
    "wtp_questions": [""]
  },
  "payment": {"whop_id": "", "paid": false, "our_fee": 0, "study_budget": 0},
  "terac": {"study_ref": "", "posted_at": ""},
  "responses": [{"tester_id": "", "segment": "", "answers": {}}],
  "report": {"themes": [], "quotes": [], "price_range": "", "recommendation": ""}
}
```
Do not rename fields without telling the team.

## Team split
- **Person 1, Money + plumbing:** Whop store, product, checkout link; payment webhook triggers the agent; fee math; owns the database and deployment.
- **Person 2, Agent brain:** prompt that turns the brief into pushback, segments, screeners, questions, and WTP questions (fills `plan`). Test on 3 fake briefs: biotech, consumer app, B2B SaaS.
- **Person 3, Terac + results:** connect Terac MCP, post the study from `plan`, pull responses into `responses`, synthesis prompt fills `report`, owns the Terac before/after measurement.
- **Person 4, Front end (Lovable):** intake form, Whop redirect, founder study page (plan + report), tester page `/study/{id}`, demo flow and backup recording.

## Checkpoints
| Time | Must have |
|---|---|
| 4:00 | Schema agreed, database live, Whop checkout link works |
| 4:45 | Agent produces a good plan from a real brief; intake form saves to DB |
| **5:15** | **One real study live on Terac, paid through Whop (hard deadline; responses take time)** |
| 5:45 | Responses flowing in, tester page working |
| 6:15 | Synthesis report visible on the founder page |
| 6:30 | Demo rehearsed, backup video recorded |

## Cut for today
- Deploying founder repos to Vercel (ask for a live URL)
- Tester accounts and startup accounts (use study links)
- Anything not needed for one complete real study end to end

## Revenue plan
Other hackathon teams are startups that need real feedback. Offer: "$15, we design and run your user study with real verified people." Get one real paying team before 5 PM.

## Terac before/after (pick one)
- **Option A:** plan from the founder's brief alone vs plan after the agent's judgment; testers rate how relevant the study was to them.
- **Option B:** feedback quality from the agent-designed questions vs a naive "what do you think?" version.

## Instructions for Claude
- Help me with my part of this project. Ask me which role I have if it isn't clear.
- Keep solutions simple and fast to build; we have hours, not days.
- Use the shared data object exactly as written.
- Never simulate external actions (payments, Terac posts) and present them as done.
- Flag anything that breaks the hackathon rules above.
