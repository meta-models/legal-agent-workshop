"""submit_memo: file the case memo.

Verification off: the memo is filed unverified and the run ends (answered).
Verification on: the memo rules (verification/verify_memo.py) run first, then the claims
check (verification/verify_claims.py). A memo that fails is refused with the problems; after
MAX_REFUSALS refused memos the run escalates to a person. A memo that passes both waits
for attorney sign-off (awaiting_signoff).
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from .request_evidence import escalate

if TYPE_CHECKING:
    from mcp_server.context import Context

MAX_REFUSALS = 3

ITEM = {
    "type": "string",
    "description": "id of an item in your checklist (set_checklist)",
}
CITATION = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "document_id": {"type": "string"},
        "page": {"type": "integer"},
        "quote": {"type": "string"},
    },
    "required": ["document_id", "page", "quote"],
}
FINDING = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "item": ITEM,
        "status": {"type": "string", "enum": ["proven", "not_proven", "escalated"]},
        "summary": {"type": "string"},
        "citations": {"type": "array", "items": CITATION, "maxItems": 3},
    },
    "required": ["item", "status", "summary", "citations"],
}

DEFINITION = {
    "type": "function",
    "name": "submit_memo",
    "description": "File the case memo: the answer to the question in 2-3 sentences, one finding per checklist item "
    "in one sentence citing its 1-3 strongest recorded facts, and the remaining gaps as a short list.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "conclusion": {"type": "string"},
            "findings": {"type": "array", "items": FINDING},
            "gaps": {"type": "string"},
        },
        "required": ["conclusion", "findings", "gaps"],
    },
}


def run(ctx: Context, args: dict) -> dict:
    memo = {
        "conclusion": str(args.get("conclusion", "")),
        "findings": args.get("findings") or [],
        "gaps": str(args.get("gaps", "")),
    }
    if not ctx.verification:
        ctx.case.file_memo(memo, "unverified")
        return {"filed": True, "memo": "unverified", "status": "answered"}
    from verification import verify_claims

    verify_memo = importlib.import_module(
        "verification.verify_memo"
    )  # yours, built in Session 2
    check, result = "memo", verify_memo.run_verification(ctx, memo)
    if result.get("passed"):
        ctx.case.record_memo_check("memo", [])
        check, result = "claims", verify_claims.run_verification(ctx, memo)
    problems = (
        []
        if result.get("passed")
        else [str(p) for p in result.get("feedback") or ["refused"]]
    )
    ctx.case.record_memo_check(check, problems)
    if problems:
        if ctx.case.memo_refusals() >= MAX_REFUSALS:
            checklist = ctx.case.data["checklist"]
            item = next(
                (k for k, v in checklist.items() if v["status"] == "open"),
                next(iter(checklist), ""),
            )
            need = (
                f"The memo was refused {ctx.case.memo_refusals()} times. Last problems: "
                + "; ".join(problems)
            )
            return escalate(ctx, item, need, "memo_refused")
        return {"error": "memo refused", "check": check, "problems": problems}
    ctx.case.file_memo(memo, "awaiting_signoff")
    return {"filed": True, "memo": "awaiting_signoff", "status": "awaiting_signoff"}
