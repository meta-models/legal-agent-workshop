"""request_evidence (verification on): escalate one checklist item to a person.

verification/verify_evidence_request.py decides whether the request is allowed.
An allowed request opens a request in the case record and stops the run (needs_input)
until a person releases evidence or replies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_kit import document_text

if TYPE_CHECKING:
    from mcp_server.context import Context

DEFINITION = {
    "type": "function",
    "name": "request_evidence",
    "description": "Escalate to the reviewer when one checklist item cannot be proven from the visible documents. "
    "Name the item and exactly what evidence is needed. The run pauses until the reviewer responds. You cannot "
    "release documents.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "item": {
                "type": "string",
                "description": "id of an item in your checklist (set_checklist)",
            },
            "need": {"type": "string"},
        },
        "required": ["item", "need"],
    },
}


def run(ctx: Context, args: dict) -> dict:
    from verification import verify_evidence_request

    item, need = str(args.get("item", "")), str(args.get("need", ""))
    check = verify_evidence_request.run_verification(ctx, {"item": item, "need": need})
    if not check["passed"]:
        return {"error": check["feedback"]}
    return escalate(ctx, item, need, "missing_evidence")


def escalate(ctx: Context, item: str, need: str, rule: str) -> dict:
    """Open a request to a person for one checklist item; the run stops (needs_input)."""
    visible = [d["id"] for d in document_text.list_documents(ctx.root)]
    request = ctx.case.open_request(item, need, rule, visible)
    return {
        "escalated": True,
        "request": request["id"],
        "item": item,
        "need": need,
        "status": "needs_input",
    }
