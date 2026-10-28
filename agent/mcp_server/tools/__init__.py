"""The agent's tools, one file per tool: its DEFINITION (what the model sees) and
run(ctx, args) (what happens when the model calls it). Served by mcp_server/server.py.

BASE_TOOLS are the six tools the agent always has. VERIFIER_TOOLS are added for runs
started with VERIFICATION=on, and with it on, set_checklist, analyze_document and
submit_memo also run the checks in agent/verification/ at their fixed points.

A result is what the model sees next. A refused call comes back as {"error": ...} so the
model can correct it. A result carries "status" only when the run must stop:
"answered" (memo filed, verification off), "needs_input" (a person must act),
"awaiting_signoff" (memo passed the checks), or "paused" (a check is not built yet).
"""

from __future__ import annotations

from typing import Any

from . import (
    analyze_document,
    check_signatures,
    flag_privileged,
    list_documents,
    record_fact,
    request_evidence,
    set_checklist,
    submit_memo,
    update_plan,
)

BASE_TOOLS = [
    "set_checklist",
    "update_plan",
    "list_documents",
    "analyze_document",
    "record_fact",
    "submit_memo",
]
VERIFIER_TOOLS = ["flag_privileged", "request_evidence", "check_signatures"]

MODULES: dict[str, Any] = {
    str(m.DEFINITION["name"]): m
    for m in (
        set_checklist,
        update_plan,
        list_documents,
        analyze_document,
        record_fact,
        submit_memo,
        flag_privileged,
        request_evidence,
        check_signatures,
    )
}
DEFINITIONS: dict[str, dict] = {
    name: module.DEFINITION for name, module in MODULES.items()
}


def names(verification: bool) -> list:
    return BASE_TOOLS + VERIFIER_TOOLS if verification else list(BASE_TOOLS)
