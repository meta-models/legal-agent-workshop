"""flag_privileged (verification on): flag a confidential lawyer-client document.

It is excluded: its facts are withdrawn, it cannot be read again or cited, and the
attorney reviews the flags at memo sign-off.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_server.context import Context

DEFINITION = {
    "type": "function",
    "name": "flag_privileged",
    "description": "Flag a confidential lawyer-client document (Confidential Doc/Info). It is excluded and can "
    "never be cited. The attorney reviews flags at memo sign-off.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"document_id": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["document_id", "reason"],
    },
}


def run(ctx: Context, args: dict) -> dict:
    flag = ctx.case.flag_privileged(
        str(args.get("document_id", "")), str(args.get("reason", ""))
    )
    return {"flagged": flag}
