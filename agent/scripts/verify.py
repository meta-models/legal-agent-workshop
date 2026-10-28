#!/usr/bin/env python3
"""Run the verification checks on a finished run's memo or checklist (the agent is not involved).

./helper verify RUN_ID --memo        # the memo rules (verification/verify_memo.py) and the claims check
./helper verify RUN_ID --checklist   # the checklist against the case's ground truth (verification/verify_checklist.py)

The same check functions the tools call. Results are saved with the run
(workspace/runs/RUN_ID/verification.json) for the console; the run itself is not changed.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(
    str(ROOT)
)  # after the test runner's own paths, so tests import the same modules

from agent_kit.case_record import CaseRecord  # noqa: E402
from agent_kit.client import make_client, MissingKeyError  # noqa: E402
from agent_kit.progress import now  # noqa: E402
from mcp_server.context import Context  # noqa: E402
from mcp_server.tools.set_checklist import normalize_result  # noqa: E402
from verification import verify_claims  # noqa: E402


def context(client, root: Path, run_id: str) -> Context:
    return Context(client, root, run_id, CaseRecord(root, run_id), True)


def verify_memo(ctx: Context) -> dict:
    filed = ctx.case.data.get("memo")
    if not filed:
        raise RuntimeError(f"{ctx.run_id} has no memo to verify")
    memo = {
        k: filed.get(k, "" if k != "findings" else [])
        for k in ("conclusion", "findings", "gaps")
    }
    rules = importlib.import_module("verification.verify_memo").run_verification(
        ctx, memo
    )
    claims = verify_claims.run_verification(ctx, memo)
    return {
        "what": "memo",
        "passed": bool(rules.get("passed") and claims.get("passed")),
        "rules": [str(p) for p in rules.get("feedback") or []],
        "claims": [str(p) for p in claims.get("feedback") or []],
    }


def verify_checklist(ctx: Context) -> dict:
    checklist = ctx.case.data["checklist"]
    if not checklist:
        raise RuntimeError(f"{ctx.run_id} has no checklist to verify")
    keys = ("question", "evidence_needed", "needs_signature_check")
    items = [{"id": k, **{f: v.get(f) for f in keys}} for k, v in checklist.items()]
    verify_checklist_ = importlib.import_module("verification.verify_checklist")
    result = normalize_result(verify_checklist_.run_verification(ctx, items))
    if result["score"] is None:
        raise RuntimeError(
            "this case has no ground truth, so its checklist cannot be checked"
        )
    return dict(result, what="checklist")


def save(root: Path, run_id: str, result: dict) -> dict:
    path = root / "workspace/runs" / run_id / "verification.json"
    try:
        saved = json.loads(path.read_text())
    except (OSError, ValueError):
        saved = []
    result = dict(result, at=now())
    path.write_text(json.dumps(saved + [result], indent=1))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run_id")
    what = parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--memo", action="store_true")
    what.add_argument("--checklist", action="store_true")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args()
    if not (ROOT / "workspace/runs" / args.run_id / "progress.json").is_file():
        sys.exit(f"no such run: {args.run_id}")
    try:
        with contextlib.redirect_stdout(sys.stderr):  # stdout carries only the result
            ctx = context(make_client(), ROOT, args.run_id)
            result = (verify_memo if args.memo else verify_checklist)(ctx)
    except (MissingKeyError, RuntimeError, FileNotFoundError) as error:
        sys.exit(str(error))
    result = save(ROOT, args.run_id, result)
    if args.json:
        print(json.dumps(result, indent=2))
    elif args.memo:
        print("MEMO " + ("passes" if result["passed"] else "fails"))
        for problem in result["rules"]:
            print(f"  rule:  {problem}")
        for problem in result["claims"]:
            print(f"  claim: {problem}")
    else:
        print(
            f"CHECKLIST {'passes' if result['passed'] else 'fails'} · score {result['score']:.0%}"
        )
        if result["feedback"]:
            print(f"  feedback: {result['feedback']}")


if __name__ == "__main__":
    main()
