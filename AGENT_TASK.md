# My part: Agent brain + Terac + results (Person 2 + Person 3)

Read `CONTEXT.md` first. This file replaces `PLANNER_TASK.md`.

## Decisions already made
- Plan is shown to the founder **before payment**.
- Founder sees an **estimated cost**, pays that on Whop. The estimate is the hard cap for Terac spend (`maximum_total_cost_cents`). If Terac's quote is higher, the agent shrinks the tester count to fit. Never spend more than the founder paid.
- After payment, the study **auto-posts and launches on Terac** (no founder approval).
- Founder picks the tester count (`brief.desired_testers`).
- Language: **Python** (the Terac cookbook is Python).
- Team Terac budget: **$100 event credits total**. Target the **general population** for speed.

## Time plan (submissions lock 6:45)
| By | Done |
|---|---|
| 4:45 | Terac MCP connected, cookbook replay runs, credits claimed |
| 5:05 | Planner v1 produces a valid plan JSON |
| **5:15** | **Real study launched on Terac** (see "First real study") |
| 5:45 | Responses arriving into `responses` |
| 6:15 | Synthesis report + before/after numbers |

If behind, cut planner polish, never the 5:15 launch.

## 1. Terac setup (first 15 min)
- Claim credits: https://terac.com/r/ghdU4NpIZ9raQFxAFs39hH63yXl8iAV2
- Install the Terac MCP in Claude Code (follow Terac's MCP install docs from the guidebook).
- Clone https://github.com/TeracAI/terac-cookbook, install with `uv`, run the oracle **replay** (no spending) to see the flow.
- Learn from the cookbook: study fields, quote, draft, launch, and the **task completion callback** our tester page must call.

## 2. Planner: `plan_study(study) -> plan`
Input: `study.startup`, `study.brief` (incl. `desired_testers`, `budget_usd`).
Output schema (Pydantic, validated):
```json
{
  "summary": "",
  "agent_pushback": [{"issue": "", "change": "", "why": ""}],
  "segments": [{"name": "", "count": 0, "why": "", "criteria": [""], "screener": [{"q": "", "qualify_if": ""}]}],
  "diversity_notes": [""],
  "tester_instructions": "",
  "est_minutes": 15,
  "est_cost_usd": 0,
  "max_cost_cents": 0,
  "total_testers": 0,
  "questions": [{"id": "q1", "text": "", "type": "text | scale_1_5 | choice", "options": [], "purpose": ""}],
  "wtp_questions": [{"id": "wtp1", "text": "", "type": "number_usd"}],
  "limitations": [""],
  "terac_study": {
    "title": "", "description": "", "business_type": "b2c | b2b",
    "num_participants": 0, "device_types": ["desktop"], "expected_days_to_complete": 1,
    "audience_note": "plain language; mapped to Terac filters (country filter required)",
    "task": {"task_type": "interview", "review_type": "auto_approve", "title": "", "description": "",
             "instructions": "", "task_url": "https://OUR_SITE/study/{study_id}"},
    "quote": {"task_description": "", "panel_description": "", "submission_count": 0,
              "timeline_hours": 3, "pay_rate_frequency": "ONE_TIME", "loi_minutes": 15}
  }
}
```
Rules:
- Structured output / tool use, never free-text parsing.
- Pushback must be **specific to the product**, not generic. If the brief is good, say why instead.
- Segment counts sum to `total_testers`. One Terac study = one audience; segments go in the panel description + screeners on our page.
- Prefer general population; if the founder asks for specialists, say they're slower/pricier today and offer a general-population proxy.
- ~1 minute per question + time to try the product = `est_minutes` = `loi_minutes`.
- WTP: 4 Van Westendorp questions adapted to the product's billing unit.
- Under ~8 testers: note WTP is directional only.
- I write the system prompt myself.

Fixtures (save outputs to `fixtures/`):
- PipetteIQ (biotech protocol error checker), persona "biologists", 20 testers, $200
- SplitNest (roommate bill splitting), persona "college students", 5 testers, $100, goal: onboarding
- ShiftSync (restaurant scheduling SaaS), persona "restaurant owners", 30 testers, $300, goal: WTP

## 3. Terac execution: `launch_study(study) -> terac_ref`
- From `plan.terac_study`: feasibility/quote, then draft, then launch, with cap = `max_cost_cents`.
- If quote total > cap: reduce `num_participants` to fit, update plan, retry once.
- Save `terac.study_ref`, `posted_at`, set `status = live`.
- Never mark launched unless Terac confirms it.

## 4. Results
- Responses come from our tester page (Person 4) into `study.responses`, each with `segment` from screeners.
- `synthesize(study) -> report`: themes (with counts), 3 to 5 quotes, WTP price range (Van Westendorp points if enough responses, otherwise "directional"), recommendation, limitations.

## 5. First real study + Terac before/after (the requirement)
Use **our own product** as the first study, general population:
- Testers read a sample founder brief and our agent's v1 plan, rate it 1 to 5 on clarity and usefulness, and say what's missing.
- I improve the planner prompt from their feedback (v2).
- If time allows, a second small study rates v2, or compare v1 vs v2 side by side in one study.
- Demo shows: v1 score, feedback themes, what changed, v2 score.
Agree the tester page with Person 4 before launching.

## Rules for Claude
- **Never run `git commit`, `git push`, or any git command that changes history. I commit and push myself.**
- Never launch a real Terac study or spend credits without asking me first.
- Never write API keys into files that get committed; use a `.env` file listed in `.gitignore`.

## Not my job
Whop checkout, intake form, founder/tester page UI, deployment.
