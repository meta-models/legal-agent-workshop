"""set_checklist: the questions that must be settled to answer the case question.

With verification on, the checklist check (verification/verify_checklist.py) runs first. A
checklist that fails is refused with the check's feedback, never the ground truth;
after MAX_TRIES the checklist is accepted, and the score and feedback stay in the case
record for the attorney.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_server.context import Context

MAX_TRIES = 3

ITEM = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "description": "snake_case id, e.g. ready_statement"},
        "question": {
            "type": "string",
            "description": "what must be established to answer the case question",
        },
        "evidence_needed": {
            "type": "string",
            "description": "what evidence would settle this item",
        },
        "needs_signature_check": {
            "type": "boolean",
            "description": "true when the item turns on who signed a document",
        },
    },
    "required": ["id", "question", "evidence_needed", "needs_signature_check"],
}

DEFINITION = {
    "type": "function",
    "name": "set_checklist",
    "description": "Set the checklist: the questions that must be settled to answer the case question, each with "
    "the evidence that would settle it. Call it first, before planning or investigating. Calling it again "
    "replaces the checklist; items that already have facts or requests must be kept.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"items": {"type": "array", "items": ITEM, "minItems": 1}},
        "required": ["items"],
    },
}


def run(ctx: Context, args: dict) -> dict:
    items = args.get("items") or []
    if ctx.verification:
        ctx.case.parse_checklist(items)  # malformed items are refused before any check
        check = normalize_result(
            importlib.import_module("verification.verify_checklist").run_verification(
                ctx, items
            )
        )
        if (
            check["score"] is not None
        ):  # None: the case has no ground truth to check against
            attempt = len(ctx.case.data["checklist_checks"]) + 1
            accepted = check["passed"] or attempt >= MAX_TRIES
            ctx.case.record_checklist_check(
                items, dict(check, attempt=attempt, accepted=accepted)
            )
            if not accepted:
                return {"error": "checklist refused", "feedback": check["feedback"]}
    return {"checklist": list(ctx.case.set_checklist(items))}


def normalize_result(result: dict) -> dict:
    """verify_checklist's result as {"passed", "score", "feedback"}."""
    if not isinstance(result, dict) or "passed" not in result:
        raise ValueError(
            "verify_checklist.run_verification must return {'passed', 'score', 'feedback'}"
        )
    passed = bool(result["passed"])
    score = result.get("score")
    try:
        score = None if score is None else round(float(score), 2)
    except (TypeError, ValueError):
        score = 1.0 if passed else 0.0
    return {
        "passed": passed,
        "score": score,
        "feedback": "" if passed else str(result.get("feedback") or ""),
    }
