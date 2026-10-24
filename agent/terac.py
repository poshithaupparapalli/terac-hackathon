"""launch_study(study, dry_run=True): quote -> draft -> (launch) on Terac.

Shapes follow Terac's REST API (https://terac.com/docs/developers/openapi.json).
dry_run=True still creates the project, feasibility request and draft on Terac
(none of these spend credits) but never calls /launch.

Usage:
    uv run python -m agent.terac fixtures/splitnest.json      # dry run
"""

import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from agent.schemas import Plan

load_dotenv()

API_BASE = "https://terac.com/api/external/v2"
PROJECT_NAME = "User Research Agent"
CONFIG_PATH = Path(__file__).resolve().parent.parent / ".terac_config.json"
LAUNCHED_STATUSES = {"pre_recruiting", "active"}

# The tester page must redirect here when a tester finishes, or the submission falls back to
# manual review instead of auto_approve. Testers arrive on task_url with ?submissionId=...&
# teracSubmissionId=...&taskId=...; only teracSubmissionId goes back. No auth, no API call.
# https://terac.com/docs/researchers/integrations/external-surveys
TERAC_COMPLETION_CALLBACK = (
    "https://terac.com/api/external/callback?teracSubmissionId={{teracSubmissionId}}&result=completed"
)


def completion_url(terac_submission_id: str) -> str:
    """TERAC_COMPLETION_CALLBACK with the tester's teracSubmissionId filled in."""
    from urllib.parse import quote

    return TERAC_COMPLETION_CALLBACK.replace("{{teracSubmissionId}}", quote(terac_submission_id, safe=""))

SCREENER = [
    {
        "key": "adult_us",
        "text": "Are you 18 or older and living in the US?",
        "pick": "one",
        "answers": [
            {"text": "Yes", "qualify_logic": "must"},
            {"text": "No", "qualify_logic": "reject"},
        ],
    }
]
US_FILTER = [{"multi_select--country": {"$in": ["US"]}}]


def log(msg: str) -> None:
    print(f"[terac] {msg}", file=sys.stderr)


class Terac:
    def __init__(self, api_key: str | None = None):
        key = api_key or os.environ.get("TERAC_API_KEY")
        if not key:
            raise RuntimeError("TERAC_API_KEY is not set (put it in .env)")
        self.http = httpx.Client(
            base_url=API_BASE, headers={"Authorization": f"Bearer {key}"}, timeout=30
        )

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        r = self.http.request(method, path, json=body)
        if r.status_code >= 400:
            raise RuntimeError(f"Terac {method} {path} -> {r.status_code}: {r.text[:500]}")
        return r.json()


def _load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}


def get_or_create_project(t: Terac) -> str:
    """Reuse one project: TERAC_PROJECT_ID env, then .terac_config.json, then by name, else create."""
    if pid := os.environ.get("TERAC_PROJECT_ID") or _load_config().get("project_id"):
        return pid
    cursor = None
    while True:
        page = t.request("GET", "/projects" + (f"?cursor={cursor}" if cursor else ""))
        for p in page["data"]:
            if p["name"] == PROJECT_NAME:
                pid = p["id"]
                break
        else:
            if page["pagination"]["has_more"]:
                cursor = page["pagination"]["next_cursor"]
                continue
            pid = t.request("POST", "/projects", {"name": PROJECT_NAME})["id"]
            log(f"created project {pid}")
        break
    CONFIG_PATH.write_text(json.dumps({**_load_config(), "project_id": pid}, indent=2))
    return pid


def _cents(cost: str) -> int:
    """costPerParticipant comes back as a string, e.g. "12.50" or "$12.50"."""
    num = re.sub(r"[^0-9.]", "", cost or "")
    if not num:
        raise RuntimeError(f"unparseable costPerParticipant: {cost!r}")
    return round(float(num) * 100)


def get_quote(t: Terac, plan: Plan, poll_seconds: int = 15, timeout_seconds: int = 900) -> dict:
    q = plan.terac_study.quote
    req = t.request(
        "POST",
        "/feasibility/requests",
        {
            "taskDescription": q.task_description,
            "panelDescription": q.panel_description,
            "submissionCount": plan.terac_study.num_participants,
            "timelineHours": q.timeline_hours,
            "payRateFrequency": q.pay_rate_frequency,
            "loiMinutes": q.loi_minutes,
        },
    )
    log(f"feasibility request {req['id']} status={req['status']}")
    deadline = time.monotonic() + timeout_seconds
    while req["status"] == "RECEIVED":
        if time.monotonic() > deadline:
            raise TimeoutError(f"quote {req['id']} not RESPONDED after {timeout_seconds}s")
        time.sleep(poll_seconds)
        req = t.request("GET", f"/feasibility/requests/{req['id']}")
    if req["status"] != "RESPONDED" or not req.get("costPerParticipant"):
        raise RuntimeError(f"quote {req['id']} ended as {req['status']}, no price")
    return req


def _opportunity_body(plan: Plan, project_id: str, feasibility_id: str, n: int) -> dict:
    ts = plan.terac_study
    return {
        "title": ts.title,
        "description": ts.description,
        "project_id": project_id,
        "num_participants": n,
        "business_type": ts.business_type,
        "device_types": ts.device_types,
        "expected_days_to_complete": ts.expected_days_to_complete,
        "feasibility_request_id": feasibility_id,
        "filters": US_FILTER,
        "screening_questions": SCREENER,
        "tasks": [
            {
                "sequence": 1,
                "task_type": ts.task.task_type,
                "review_type": ts.task.review_type,
                "task_url": ts.task.task_url,
                "title": ts.task.title,
                "description": ts.task.description,
                "duration_minutes": plan.est_minutes,
            }
        ],
    }


def _shrink_plan(plan: Plan, n: int) -> None:
    plan.total_testers = n
    plan.terac_study.num_participants = n
    plan.terac_study.quote.submission_count = n


def launch_study(study: dict, dry_run: bool = True, t: Terac | None = None) -> dict:
    """Quote, draft and (unless dry_run) launch study["plan"] on Terac. Updates study in place."""
    t = t or Terac()
    plan = Plan.model_validate(study["plan"])
    cap = plan.max_cost_cents
    if not plan.terac_study.task.task_url.startswith("https://") or "OUR_SITE" in plan.terac_study.task.task_url:
        raise RuntimeError(f"task_url is not a real HTTPS tester page: {plan.terac_study.task.task_url}")

    project_id = get_or_create_project(t)
    quote = get_quote(t, plan)
    cpp = _cents(quote["costPerParticipant"])
    n = plan.terac_study.num_participants
    log(f"quote: {cpp / 100:.2f} USD/participant x {n} = {cpp * n / 100:.2f} (cap {cap / 100:.2f})")

    if cpp * n > cap:
        fit = cap // cpp
        if fit < 1:
            raise RuntimeError(f"cap {cap}c cannot cover one participant at {cpp}c")
        log(f"quote over cap: reducing num_participants {n} -> {fit}")
        n = fit
        _shrink_plan(plan, n)

    body = _opportunity_body(plan, project_id, quote["id"], n)
    draft = t.request("POST", "/opportunities", body)
    draft = t.request("GET", f"/opportunities/{draft['id']}")  # re-read the stored total
    total = draft["pricing"]["total_cost_cents"]
    log(f"draft {draft['id']} status={draft['status']} total={total / 100:.2f} USD")
    if total > cap:
        raise RuntimeError(f"draft total {total}c exceeds cap {cap}c; not launching")
    if (funding := draft.get("funding")) and not funding.get("affordable", True):
        log(f"WARNING: Terac balance does not cover this (shortfall {funding['shortfall_cents']}c)")

    study["plan"] = plan.model_dump()
    study["terac"]["study_ref"] = draft["id"]
    result = {
        "study_ref": draft["id"],
        "status": draft["status"],
        "total_cost_cents": total,
        "num_participants": n,
        "draft_editor": draft.get("links", {}).get("dashboard", {}).get("draft_editor"),
        "launched": False,
    }

    if dry_run:
        log("DRY RUN: would POST /opportunities/%s/launch. Draft body sent:" % draft["id"])
        print(json.dumps(body, indent=2), file=sys.stderr)
        return result

    launched = t.request("POST", f"/opportunities/{draft['id']}/launch", {})
    result["status"] = launched["status"]
    if launched["status"] not in LAUNCHED_STATUSES:
        raise RuntimeError(f"launch returned status {launched['status']}; not treating as launched")
    result["launched"] = True
    study["terac"]["posted_at"] = datetime.now(UTC).isoformat()
    study["status"] = "live"
    log(f"LAUNCHED {draft['id']} status={launched['status']}")
    return result


if __name__ == "__main__":
    path = Path(sys.argv[1])
    study = json.loads(path.read_text())
    study["plan"] = json.loads(path.with_suffix(".plan.json").read_text())
    print(json.dumps(launch_study(study, dry_run=True), indent=2))
