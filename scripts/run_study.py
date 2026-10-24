"""Plan and launch one study from Supabase.

    python scripts/run_study.py STUDY_ID                 # plan if needed, then Terac dry run
    python scripts/run_study.py STUDY_ID --live          # really launch (spends Terac credits)
    python scripts/run_study.py STUDY_ID --max-usd 20    # cap when payment.study_budget is unset

Needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env (service role: server side only).
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from agent.planner import plan_study  # noqa: E402
from agent.terac import launch_study  # noqa: E402

load_dotenv()


class Studies:
    def __init__(self):
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            sys.exit("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        self.http = httpx.Client(
            base_url=f"{url}/rest/v1",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=30,
        )

    def get(self, study_id: str) -> dict:
        r = self.http.get("/studies", params={"study_id": f"eq.{study_id}", "select": "*"})
        r.raise_for_status()
        rows = r.json()
        if not rows:
            sys.exit(f"study {study_id} not found")
        return rows[0]

    def update(self, study_id: str, fields: dict) -> None:
        r = self.http.patch(
            "/studies",
            params={"study_id": f"eq.{study_id}"},
            json=fields,
            headers={"Prefer": "return=minimal"},
        )
        r.raise_for_status()


def has_plan(plan: dict | None) -> bool:
    return bool(plan and plan.get("summary") and plan.get("terac_study"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("study_id")
    ap.add_argument("--live", action="store_true", help="really launch on Terac (default: dry run)")
    ap.add_argument("--max-usd", type=float, help="Terac spend cap if payment.study_budget is unset")
    ap.add_argument("--unpaid-ok", action="store_true",
                    help="allow --live on a study Whop hasn't marked paid (e.g. our own credit-funded study)")
    args = ap.parse_args()

    db = Studies()
    study = db.get(args.study_id)
    payment = study.get("payment") or {}

    # The backend stores the tier's tester count as brief.tester_count.
    brief = study.setdefault("brief", {})
    if brief.get("tester_count") and not brief.get("desired_testers"):
        brief["desired_testers"] = brief["tester_count"]

    if has_plan(study.get("plan")):
        print(f"[run_study] using existing plan ({study['plan'].get('total_testers')} testers)")
    else:
        print("[run_study] no plan yet; running plan_study")
        study["plan"] = plan_study(study).model_dump()
        db.update(args.study_id, {"plan": study["plan"]})
        print("[run_study] plan saved")

    # Spend cap: what the founder actually funded, else an explicit --max-usd.
    budget = payment.get("study_budget") or 0
    if budget > 0:
        cap_usd, source = float(budget), "payment.study_budget"
    elif args.max_usd:
        cap_usd, source = args.max_usd, "--max-usd"
    else:
        sys.exit("no payment.study_budget on this study; pass --max-usd to set a Terac spend cap")
    study["plan"]["max_cost_cents"] = round(cap_usd * 100)
    print(f"[run_study] Terac cap ${cap_usd:.2f} (from {source})")

    # Rebuild task_url so an old plan picks up the current TESTER_BASE_URL.
    base = os.environ.get("TESTER_BASE_URL", "").rstrip("/")
    if not base.startswith("https://") or "OUR_SITE" in base:
        sys.exit("TESTER_BASE_URL must be the deployed https:// site (e.g. https://vera.vercel.app)")
    study["plan"]["terac_study"]["task"]["task_url"] = f"{base}/study/{args.study_id}"

    if args.live and not payment.get("paid") and not args.unpaid_ok:
        sys.exit("study is not marked paid by Whop; refusing --live (use --unpaid-ok for our own study)")

    result = launch_study(study, dry_run=not args.live)
    print(json.dumps(result, indent=2))

    if result["launched"]:
        db.update(args.study_id, {
            "plan": study["plan"],
            "terac": study["terac"],
            "status": "live",
        })
        print(f"[run_study] saved terac.study_ref={study['terac']['study_ref']} and status=live")
    else:
        print("[run_study] dry run: nothing written to Supabase, nothing launched")


if __name__ == "__main__":
    main()
