# Escalation

When a run stops for a person, what the person sees, and how the run resumes. All pre-built: the tools in `mcp_server/tools/` open the requests and `agent_kit/progress.py` resumes; whether an escalation is allowed is decided by the checks in `VERIFICATION.md`.

## When a run escalates (verification on)

| Trigger | Rule | What unblocks it |
|---|---|---|
| The agent calls `request_evidence` and `verification/verify_evidence_request.py` allows it | `missing_evidence` | The reviewer releases documents into the inbox (`world/release.py` or the console), or replies (`./helper review RUN --answer R1 --notes "..."`) |
| The memo is refused 3 times | `memo_refused` | The reviewer replies with guidance |
| The memo passes the memo rules and the claims check | memo sign-off | The attorney approves, or rejects with notes (`./helper review RUN --approve` / `--reject --notes "..."`) |

Every escalation names one checklist item. A run that stops for a person makes no model calls until someone acts.

## Handoff

The console shows the reviewer the blocked item, the rule that fired, the documents already read, the one specific request, and the verified facts so far.

## Resume

`./helper run --resume RUN_ID` continues the same run from its saved progress (`progress.resume()`):

- **After a request**: resumes only if new documents appeared or the reviewer replied; otherwise it is refused with no model call. The agent gets a message with the reply and the released document IDs.
- **After sign-off**: approve ends the run as `done` with no model call; reject sends the attorney's notes to the agent, which submits a revised memo.
- **After the turn limit** (`paused`): the agent is told it has more turns.
