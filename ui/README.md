# Agent Console (`ui/`)

A pre-built browser UI for the legal agent workshop. It ships in the workshop repository and shows whatever agent participants built with Muse Code: start runs, watch the plan-act-observe timeline, see the agent's checklist and how each item is proven, the signature checks, and act as the reviewer (release evidence, answer a request, approve or reject the memo).

Participants never build or edit it, and it is outside `agent/`, so Muse Code cannot see it.

## Run

From the `legal-agent-workshop` folder:

```bash
python3 ui/ui.py
# open http://127.0.0.1:8765
```

It finds the workshop automatically (the folder that contains `ui/`). `--workshop PATH` points it at a different clone; `--port` changes the port. Python standard library only. Binds to 127.0.0.1.

## Making a run easy to follow

- **Tools Available** (left): every tool, with its parameters. The three marked **verification on** (`flag_privileged`, `request_evidence`, `check_signatures`) are greyed out unless the selected run has verification on; with no run selected, the panel follows `VERIFICATION` in `agent/.env`.
- **Case** (header): pick any folder under `cases/` that has an `objective.md`. Switching sets `CASE_DIR` in `agent/.env` and resets the inbox to that case's documents (runs are kept); it is disabled while the agent runs.
- **The agent's assignment** (centre): the selected case's `objective.md` (its path is shown in the header), rendered as Markdown. Click the header to collapse it.
- **Checklist** (right): the checklist the agent drafted, item by item: the question, what evidence settles it, its status (open / proven / escalated), each fact as it is recorded (document · page · quote), and the signature verdict on items that need one. With a ground-truth checklist, the header shows the coverage score and the feedback the agent got (the agent itself never sees the score).
- **Timeline**: one card per turn with three rows. **Plan**: the agent's model call (tokens). **Act**: the one tool it chose and its arguments; "show details" lists one line per document read (evidence records, how many verified) or per page SAM looked at. **Observe**: what came back, coloured by outcome (checklist set or refused with feedback, fact recorded, refused, memo refused by the memo rules or the claims check, escalated, signature verdict). Click a turn's header for **what the model saw and decided**.
- **Step through turns**: tick it before Start; the run pauses before every turn until you click **Next turn** (or **Run to end**). Use it for the first run in Session 1.
- **Run** (below the timeline): pick a run, its status, counts (turns, tool calls, agent tokens, facts, failed checks, escalations, flags), and the agent's terminal output.

## What it uses from the workshop

- Reads: `agent/workspace/runs/<run>/progress.json` (the conversation and each turn's tokens, saved by `agent_kit.progress`), `agent/workspace/case_records/<run>.json`, page images, `agent/.env` (only for CASE_DIR, the verification setting, and whether a key is set; the key itself is never sent to the browser), and the case folder's objective and page images.
- **Verify this run** (finished runs without verification): **Verify the memo** and **Verify the checklist** run the checks on the work the run already did (`./helper verify`); **Continue from the checklist, verification on** creates a new run from the checklist step (`./helper branch`) and selects it.
- Runs: `./helper run [--resume]`, `./helper review`, `./helper verify`, `./helper branch`, `./helper reset`, `./helper describe`, `world/release.py`.
- Writes `agent/workspace/control.json` (step mode), which `agent_kit.progress` reads after each saved turn, and the `CASE_DIR` line of `agent/.env` when you switch case (nothing else in `.env` is touched).
- Never imports the participant's agent.

## A typical Session 2 flow in the console

1. Select the Session 1 run. **Verify the memo**: the memo rules and the claims check list what it misses. **Verify the checklist**: the coverage score and the feedback.
2. **Continue from the checklist, verification on**: a new run starts with the Session 1 checklist refused with feedback. **Resume this run**: the agent revises the checklist, investigates, has an early memo refused, and escalates.
3. Handoff card → **Release follow-up evidence** → **Resume this run**.
4. The run reads the new documents, proves the open items, checks the certification's signature against a page the signer genuinely signed (`check_signatures` is a placeholder for now and reports it unclear, so the memo names the signature as a gap and the sign-off card shows a signature flag), and files a memo that passes the memo rules and the claims check.
5. Sign-off card → **Approve** (or reject with notes, which sends it back to the agent). Compare with the Session 1 run.
