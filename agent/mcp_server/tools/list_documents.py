"""list_documents: the documents currently released to the inbox."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agent_kit import document_text

if TYPE_CHECKING:
    from mcp_server.context import Context

DEFINITION = {
    "type": "function",
    "name": "list_documents",
    "description": "List the documents currently released to the inbox.",
    "parameters": {
        "type": "object",
        "additionalProperties": False,
        "properties": {},
        "required": [],
    },
}


def run(ctx: Context, args: dict) -> dict:
    return {
        "documents": [
            {k: d[k] for k in ("id", "modality", "pages")}
            for d in document_text.list_documents(ctx.root)
        ]
    }
