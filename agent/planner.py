"""plan_study(study) -> Plan, using Claude structured output.

Usage:
    uv run python -m agent.planner fixtures/pipetteiq.json   # writes fixtures/pipetteiq.plan.json
"""

import json
import os
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from pydantic import ValidationError

from agent.schemas import Plan, PlanDraft, TeracQuote, TeracStudy, TeracTask

load_dotenv()

MODEL = os.environ.get("PLANNER_MODEL", "claude-opus-5-5")
EFFORT = "low"  # thinking can't be disabled on Opus 5.5; low effort keeps it short
MAX_TOKENS = 8000  # a full plan is ~3-5k tokens

SYSTEM_PROMPT = """You are a senior user researcher who designs studies for early-stage startups. A founder gives you a brief. You design a study that gets them real, useful feedback from real people. You respect what the founder clearly asked for, fill in what they left open, and flag real risks.

Return the plan in the required JSON schema.

## Step 1: Understand the product
- What does it do, who uses it, and how does it (or would it) make money?
- What is the founder actually trying to learn? Restate it in one sentence at the start of "summary".

## Step 2: Respect the founder, fill the gaps
Sort everything in the brief into two kinds:
- EXPLICIT: the founder clearly stated it (a specific audience, tester count, budget, specific questions). Keep these exactly as given. Never change an explicit choice.
- OPEN: the founder left it vague, general, or blank (e.g. "general feedback", "people who might use it", no questions given). You decide these using your research judgment.

For EXPLICIT choices: if you see a real risk, add an agent_note with type "suggestion" and applied=false. Do not apply it to the plan. Real risks include:
- They asked for specialists, who are slower and more expensive to recruit today.
- The budget per tester (budget / testers) looks too low for the time and expertise asked.
- The person who pays for the product isn't in their audience, so price feedback may be unreliable.
- The tester count is under about 8, so price results will be directional only.
- Their stated goal doesn't fit their chosen audience.

For OPEN parts: fill them in, and record each decision as an agent_note with type "filled_gap" and applied=true. Consider:
- Buyer vs user: if different people use it and pay for it, include both.
- Missing people: users of a competitor or workaround, people who tried similar tools and quit, true beginners, skeptics.
- Whether general-population testers can answer these questions well (prefer them when they can).
- Questions the founder didn't think to ask.

Every agent_note must name something specific to THIS product or market: "issue" (what's wrong or missing), "change" (what you did or propose), "why" (what bad data it prevents). Never write generic advice like "consider a broader audience" or "get diverse feedback". If the brief is clear and sound, return no suggestions and explain why it's sound in "summary".

## Step 3: Design the group (segments)
- Segment counts must add up exactly to the founder's tester count.
- Each segment needs criteria a recruiter can verify, and 1 to 2 screener questions with a clear qualify_if.
- If the audience is open, no single segment should exceed 60% unless the market is genuinely that narrow; explain if so.
- diversity_notes: say what you balanced (experience level, current tools, company size, region, age range where relevant).

## Step 4: Write the questions
- 6 to 10 questions that directly serve the founder's goal. Weight them toward the goal: an onboarding goal means mostly first-use and confusion questions; a pricing goal means more value and WTP questions.
- Mix types: "text" for why/how, "scale_1_5" for comparable ratings, "choice" for categories (fill options).
- Ask about real past behavior ("how do you handle this today?") before opinions.
- No leading questions.
- Include at least one question the founder didn't think to ask, and state its purpose.

## Step 5: Willingness to pay
Write exactly four Van Westendorp questions, adapted to how this product would be billed (per month, per seat, one time, per use):
1. At what price would this be so cheap you'd doubt its quality?
2. At what price would it feel like a bargain?
3. At what price would it start to feel expensive, though you'd still consider it?
4. At what price would it be too expensive to consider?
Use type "number_usd".

## Step 6: Study logistics
- tester_instructions: plain language, step by step, for someone who has never heard of the product. Include trying the product before answering.
- est_minutes: about 1 minute per question plus time to try the product. Keep it under 20 when possible.
- est_cost_usd: a realistic estimate that does not exceed the founder's budget. General population is cheaper than specialists.
- terac_study:
  - business_type "b2c" for general population, "b2b" only if the plan genuinely needs professionals.
  - description must be 280 characters or fewer.
  - expected_days_to_complete must be 5 (Terac's minimum; speed comes from quote.timeline_hours).
  - quote.timeline_hours: 3. quote.loi_minutes = est_minutes. quote.pay_rate_frequency "ONE_TIME".
  - audience_note and quote.panel_description: plain-language description of who to recruit, including country (default US).
  - task: task_type "interview", review_type "auto_approve", clear title, description, and instructions.

## Honesty
- Never claim the plan is validated or that results will be statistically significant.
- Put real limitations in "limitations".
"""


def _user_message(study: dict) -> str:
    return (
        "Design the user study for this startup. Input JSON:\n\n"
        + json.dumps({"startup": study["startup"], "brief": study["brief"]}, indent=2)
    )


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def build_plan(draft: PlanDraft, study: dict) -> tuple[Plan, list[str]]:
    """Add terac_study and max_cost_cents in code. Returns the plan and warnings to log."""
    warnings = []
    seg_total = sum(s.count for s in draft.segments)
    if seg_total != draft.total_testers:
        warnings.append(f"segment counts sum to {seg_total}, total_testers was {draft.total_testers}")
        draft.total_testers = seg_total
    desired = study["brief"].get("desired_testers")
    if desired is not None and desired != draft.total_testers:
        warnings.append(f"plan has {draft.total_testers} testers, founder asked for {desired}")
    if len(draft.wtp_questions) != 4:
        warnings.append(f"expected 4 Van Westendorp questions, got {len(draft.wtp_questions)}")

    name = study["startup"]["name"]
    n = draft.total_testers
    base = os.environ.get("TESTER_BASE_URL", "https://OUR_SITE").rstrip("/")
    task_url = f"{base}/study/{study.get('study_id') or '{study_id}'}"
    description = _truncate(
        f"Try {name}, a new product, and answer {len(draft.questions) + len(draft.wtp_questions)} "
        f"short questions about it. About {draft.est_minutes} minutes.",
        280,
    )
    panel = f"US adults (18+), general population. Segments: " + "; ".join(
        f"{s.count} x {s.name} ({', '.join(s.criteria)})" for s in draft.segments
    )
    terac_study = TeracStudy(
        title=_truncate(f"Try {name} and share your feedback", 200),
        description=description,
        business_type="b2c",
        num_participants=n,
        device_types=["desktop"],
        expected_days_to_complete=5,
        audience_note=panel,
        task=TeracTask(
            task_type="interview",
            review_type="auto_approve",
            title=f"Try {name} and answer the questions",
            description=description,
            instructions=draft.tester_instructions,
            task_url=task_url,
        ),
        quote=TeracQuote(
            task_description=(
                f"Unmoderated product test: try {name} ({study['startup']['product_url']}) and answer "
                f"{len(draft.questions)} feedback questions and 4 pricing questions on our web page. "
                f"About {draft.est_minutes} minutes."
            ),
            panel_description=panel,
            submission_count=n,
            timeline_hours=3,
            pay_rate_frequency="ONE_TIME",
            loi_minutes=draft.est_minutes,
        ),
    )
    plan = Plan(
        **draft.model_dump(),
        max_cost_cents=round(draft.est_cost_usd * 100),
        terac_study=terac_study,
    )
    return plan, warnings


def _check_stop(response) -> None:
    if response.stop_reason == "refusal":
        raise RuntimeError(f"planner refused: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("planner hit max_tokens before finishing the plan")


def _draft_structured(client: anthropic.Anthropic, study: dict) -> PlanDraft:
    response = client.messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": EFFORT},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _user_message(study)}],
        output_format=PlanDraft,
    )
    _check_stop(response)
    return response.parsed_output


def _draft_json(client: anthropic.Anthropic, study: dict) -> PlanDraft:
    """Fallback without constrained decoding: JSON in the prompt, Pydantic validation, one retry."""
    schema = json.dumps(PlanDraft.model_json_schema())
    messages = [{
        "role": "user",
        "content": _user_message(study)
        + "\n\nReturn ONLY a JSON object (no prose, no code fences) matching this JSON schema:\n"
        + schema,
    }]
    for attempt in range(2):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            output_config={"effort": EFFORT},
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        _check_stop(response)
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return PlanDraft.model_validate_json(text)
        except ValidationError as e:
            if attempt:
                raise
            messages += [
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": f"That JSON failed validation:\n{e}\nReturn the corrected JSON only."},
            ]


def plan_study(study: dict, client: anthropic.Anthropic | None = None) -> Plan:
    """Turn study.startup + study.brief into a validated Plan."""
    client = client or anthropic.Anthropic()
    try:
        draft = _draft_structured(client, study)
    except anthropic.BadRequestError as e:
        if "grammar" not in str(e):
            raise
        print("[planner] schema too large for structured output; using JSON fallback", file=sys.stderr)
        draft = _draft_json(client, study)
    plan, warnings = build_plan(draft, study)
    for w in warnings:
        print(f"[planner] warning: {w}", file=sys.stderr)
    return plan


if __name__ == "__main__":
    path = Path(sys.argv[1])
    start = time.monotonic()
    plan = plan_study(json.loads(path.read_text()))
    print(f"[planner] {MODEL} effort={EFFORT}: {time.monotonic() - start:.1f}s", file=sys.stderr)
    out = path.with_suffix(".plan.json")
    out.write_text(plan.model_dump_json(indent=2))
    print(f"wrote {out}")
