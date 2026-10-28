"""record_fact: record one piece of evidence for one checklist item in the case record.

Refused unless the quote is exactly on that page of an analyzed, non-confidential
document; at most 3 facts per item. The result says which items are still open.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_server.context import Context

DEFINITION = {
    "type": "function",
    "name": "record_fact",
    "description": "Record evidence for one checklist item in the case record. Refused unless the quote appears "
    "exactly on that page of an analyzed, non-confidential document. At most 3 facts per item. The result says "
    "which items are still open.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "item": {
                "type": "string",
                "description": "id of an item in your checklist (set_checklist)",
            },
            "document_id": {"type": "string"},
            "page": {"type": "integer"},
            "quote": {"type": "string"},
            "claim": {"type": "string"},
        },
        "required": ["item", "document_id", "page", "quote", "claim"],
    },
}


def run(ctx: Context, args: dict) -> dict:
    fact = ctx.case.record_fact(
        str(args.get("item", "")),
        str(args.get("document_id", "")),
        int(args.get("page") or 0),
        str(args.get("quote", "")),
        str(args.get("claim", "")),
    )
    return {"recorded": fact}
