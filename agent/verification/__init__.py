"""The verification layer (VERIFICATION=on): every check, in one place. Each file has one
entry point, run_verification(ctx, work) -> {"passed": bool, "feedback": ..., ...}. The
tools in mcp_server/tools/ call them at fixed points, so the agent cannot skip them;
./helper verify runs them on a saved run. See VERIFICATION.md.

- verify_checklist.py          you build: the checklist against the case's ground truth (set_checklist)
- verify_memo.py               you build: the memo rules (submit_memo)
- verify_claims.py             pre-built: is each finding supported by its quotes? (submit_memo, after verify_memo)
- verify_evidence_request.py   pre-built: is an evidence request allowed? (request_evidence)

ctx carries ctx.client (the OpenAI client), ctx.root (the agent folder), and ctx.case (the
run's case record).
"""
