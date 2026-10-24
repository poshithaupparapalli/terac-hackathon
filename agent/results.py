"""Pull Terac submissions and synthesize study.responses into a report.

Research answers come from our tester page into study["responses"]; Terac's submissions
endpoint only has status and screener answers, not the study answers.

Usage:
    uv run python -m agent.results study.json    # writes study.report.json
"""

import json
import re
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from agent.schemas import Plan, Report, Synthesis
from agent.terac import Terac

load_dotenv()

MODEL = "claude-opus-5-5"
DIRECTIONAL_UNDER = 8

SYSTEM_PROMPT = """You synthesize user research responses for a startup founder.
- Themes: group what testers actually said. count = number of distinct testers who raised it. Order by count.
- Quotes: 3 to 5 short excerpts copied verbatim from the answers (no edits, no stitching), each with its tester_id and segment. Pick ones that show the main themes and at least one critical view.
- Recommendation: 2 to 4 sentences on what the founder should do next, grounded in the responses and the price analysis you are given.
- Limitations: sample size, who was and wasn't in the sample, self-reported vs observed behaviour, and anything else that limits how far the founder should trust this.
Never claim statistical significance. Do not invent responses or numbers."""


def fetch_submissions(study: dict, t: Terac | None = None) -> list[dict]:
    """GET /opportunities/{id}/submissions, all pages."""
    t = t or Terac()
    opp = study["terac"]["study_ref"]
    if not opp:
        raise RuntimeError("study has no terac.study_ref")
    out, cursor = [], None
    while True:
        page = t.request(
            "GET", f"/opportunities/{opp}/submissions" + (f"?cursor={cursor}" if cursor else "")
        )
        out += page["data"]
        if not page["pagination"]["has_more"]:
            return out
        cursor = page["pagination"]["next_cursor"]


def _usd(value) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    m = re.search(r"\d+(?:\.\d+)?", str(value or "").replace(",", ""))
    return float(m.group()) if m else None


def _crossing(prices: list[float], f, g) -> float | None:
    """First price where f(p) - g(p) changes sign (linear interpolation)."""
    prev = None
    for p in prices:
        d = f(p) - g(p)
        if d == 0:
            return p
        if prev is not None and (prev[1] < 0) != (d < 0):
            p0, d0 = prev
            return round(p0 + (p - p0) * (d0 / (d0 - d)), 2)
        prev = (p, d)
    return None


def van_westendorp(plan: Plan, responses: list[dict]) -> dict:
    """Classic Van Westendorp points from wtp1..wtp4 (too cheap, bargain, expensive, too expensive)."""
    ids = [q.id for q in plan.wtp_questions]
    rows = []
    for r in responses:
        vals = [_usd(r.get("answers", {}).get(i)) for i in ids]
        if len(vals) == 4 and None not in vals:
            rows.append(vals)
    n = len(rows)
    result = {"n": n, "directional": n < DIRECTIONAL_UNDER}
    if n == 0:
        return result
    prices = sorted({v for row in rows for v in row})
    too_cheap = lambda p: sum(r[0] >= p for r in rows) / n  # noqa: E731
    cheap = lambda p: sum(r[1] >= p for r in rows) / n  # noqa: E731
    expensive = lambda p: sum(r[2] <= p for r in rows) / n  # noqa: E731
    too_exp = lambda p: sum(r[3] <= p for r in rows) / n  # noqa: E731
    result |= {
        "pmc": _crossing(prices, too_cheap, lambda p: 1 - cheap(p)),
        "pme": _crossing(prices, too_exp, lambda p: 1 - expensive(p)),
        "opp": _crossing(prices, too_cheap, too_exp),
        "ipp": _crossing(prices, cheap, expensive),
        "median_bargain": sorted(r[1] for r in rows)[n // 2],
        "median_expensive": sorted(r[2] for r in rows)[n // 2],
    }
    return result


def _price_range(vw: dict, unit: str) -> str:
    """Whole dollars, low–high first: the founder page reads the first two numbers as the range."""
    if vw["n"] == 0:
        return "No price answers yet"
    unit = f" {unit}" if unit else ""
    label = f"directional, n={vw['n']}" if vw["directional"] else f"n={vw['n']}"
    if vw.get("pmc") is not None and vw.get("pme") is not None:
        s = f"${round(vw['pmc'])}–${round(vw['pme'])}{unit} acceptable range"
        if vw.get("opp") is not None:
            s += f", optimal around ${round(vw['opp'])}"
        return f"{s} ({label})"
    return (
        f"${round(vw['median_bargain'])}–${round(vw['median_expensive'])}{unit}: bargain to "
        f"getting expensive, median answers ({label}; curves did not cross)"
    )


def synthesize(study: dict, client: anthropic.Anthropic | None = None) -> Report:
    client = client or anthropic.Anthropic()
    plan = Plan.model_validate(study["plan"])
    responses = study["responses"]
    if not responses:
        raise RuntimeError("no responses to synthesize")
    vw = van_westendorp(plan, responses)
    unit = plan.wtp_questions[0].text if plan.wtp_questions else ""
    unit = "per month" if "month" in unit.lower() else ""

    payload = {
        "startup": study["startup"],
        "goal": study["brief"].get("feedback_goals"),
        "questions": [q.model_dump() for q in plan.questions],
        "wtp_questions": [q.model_dump() for q in plan.wtp_questions],
        "price_analysis": vw,
        "responses": responses,
    }
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(payload, indent=2)}],
        output_format=Synthesis,
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"synthesis refused: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("synthesis hit max_tokens")
    out = response.parsed_output

    # Keep only quotes that really appear in that tester's answers.
    answers = {r["tester_id"]: json.dumps(r.get("answers", {}), ensure_ascii=False) for r in responses}
    kept = [q for q in out.quotes if q.text.strip() and q.text.strip() in answers.get(q.tester_id, "")]
    if len(kept) < len(out.quotes):
        print(f"[results] dropped {len(out.quotes) - len(kept)} non-verbatim quotes", file=sys.stderr)
    out.quotes = kept

    limitations = list(out.limitations)
    if vw["directional"]:
        limitations.insert(0, f"Only {vw['n']} price responses: the price range is directional.")
    report = Report(**out.model_dump(exclude={"limitations"}), limitations=limitations,
                    price_range=_price_range(vw, unit))
    study["report"] = report.model_dump()
    return report


if __name__ == "__main__":
    path = Path(sys.argv[1])
    report = synthesize(json.loads(path.read_text()))
    out = path.with_suffix(".report.json")
    out.write_text(report.model_dump_json(indent=2))
    print(f"wrote {out}")
