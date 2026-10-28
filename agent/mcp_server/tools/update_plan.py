"""update_plan: the investigation plan. Nothing is stored; the plan stays in the conversation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_server.context import Context

DEFINITION = {
    "type": "function",
    "name": "update_plan",
    "description": "Replace the investigation plan. Cover every checklist item; say what you will check next for each.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"plan": {"type": "array", "items": {"type": "string"}}},
        "required": ["plan"],
    },
}


def run(ctx: Context, args: dict) -> dict:
    return {"plan": [str(step) for step in args.get("plan") or []]}
