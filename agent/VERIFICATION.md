# Verification layer

On for runs started with `VERIFICATION=on` in `.env`. Every check is one file in `verification/` with one entry point, `run_verification(ctx, work) -> {"passed": bool, "feedback": ...}`. The tools in `mcp_server/tools/` call them at fixed points, so the agent cannot skip them. You build two; the rest is pre-built.

| When | File | Check | Built by | On failure |
|---|---|---|---|---|
| `set_checklist` | `verification/verify_checklist.py` | Does the checklist cover the case's ground truth? Muse Spark marks each ground-truth item covered or not; code turns that into a score | You | Refused with feedback only (never the ground truth). After 3 tries the checklist is accepted, and the score and feedback are kept for the attorney. |
| `request_evidence` | `verification/verify_evidence_request.py` | The item is on the checklist and not already proven, and every visible, non-confidential document has been read | Pre-built | Refused with the reason |
| `submit_memo` | `verification/verify_memo.py` | Every item has a finding and is proven or escalated; a finding marked proven has a recorded fact and cites it; every citation matches a recorded fact; nothing confidential is cited; a signature item marked proven has a consistent signature check on a document it cites; no evidence request is still open | You | Refused with the problems |
| `submit_memo` | `verification/verify_claims.py` | Each finding is supported by its quotes (one Muse Spark call per memo, after `verify_memo.py` passes) | Pre-built | Refused with the claims |
| 3 refused memos | | | Pre-built | Escalated to a person |
| The memo passes | | Pause for attorney sign-off | Pre-built | Rejected: the notes go back to the agent |

Also pre-built with verification on: `flag_privileged`, `request_evidence`, and `check_signatures`, which compares a signature with a reference page the agent names (a placeholder for now that reports every signature as consistent; anything else becomes a flag for the attorney); a flagged document cannot be read again. Always: at most 3 facts per checklist item and 3 citations per finding.

The ground truth stays outside this folder; `load_reference(root)` at the top of `verify_checklist.py` (pre-built) reads it. Your feedback goes to the agent as written, so it must point to what is missing without quoting, paraphrasing, or counting the ground-truth items.

## What you build

```python
# verification/verify_checklist.py
def run_verification(ctx, items: list) -> dict:
    """{"passed": bool, "score": float, "feedback": str}"""

# verification/verify_memo.py
def run_verification(ctx, memo: dict) -> dict:
    """{"passed": bool, "feedback": [problem, ...]}"""
```

Each file's docstring has the full spec. Until a check is built, a run with verification on stops at it, and `./helper test --verification` shows what is missing.

## On work already done

`./helper verify RUN_ID --memo` and `./helper verify RUN_ID --checklist` run the same checks on a finished run (the agent is not involved; the run is not changed). `./helper branch RUN_ID` starts a new run with verification on from the run's checklist step; resume it to continue.
