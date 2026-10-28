# Legal Agent Workshop

Two working sessions. Participants clone this repository and launch Muse Code from `agent/` only; `cases/`, `world/`, and `solutions/` stay outside Muse Code's workspace. First you build a general legal agent; then you point it at a case.

> Note: this branch implements the agent's tools as MCP servers; everything else is the same as `main`.

- **Session 1 — Build the agent:** the agentic loop, in plain OpenAI Python SDK code, on a pre-built kit (one file per tool, Files API document reading, a case-management system with quote-checked facts). The agent drafts a checklist, plans, investigates, and ends with an unverified memo.
- **Session 2 — Make it trustworthy:** first verify the Session 1 memo and checklist and see what they miss (`./helper verify`). Then build the two checks of the verification layer (the checklist against the case's ground truth, and the memo rules), which the kit runs outside the agent's control, and continue the Session 1 run from its checklist with verification on (`./helper branch`): refusals, escalation, release of new evidence, resume, and attorney sign-off.

The Agent Console in `ui/` (pre-built) shows any run live: `python3 ui/ui.py`, then open http://127.0.0.1:8765.

## Start

```bash
git clone https://github.com/meta-models/legal-agent-workshop.git
cd legal-agent-workshop/agent
cp .env.example .env      # add MODEL_API_KEY; CASE_DIR points at ../cases/northbridge-v-caldera
./helper setup            # creates .venv with the OpenAI Python SDK, copies the case's documents, checks the key
muse
```

## Start Muse Code

From `agent/`, run `muse`. Your first message, and again after any restart or new session, is the ground-rules prompt in `HANDBOOK.md`, section 1.7.

## Structure

- `HANDBOOK.md` — the participant handbook: setup, Session 1, then Session 2 step by step. It holds the ground-rules prompt for Muse Code (1.7).
- `agent/` — starter code and the only Muse Code workspace: a general legal agent, no case inside. See `agent/README.md`.
- `cases/northbridge-v-caldera/` — the case you hand the agent: `objective.md` and `documents/`. A new case is just a folder with an objective and its documents.
- `ground_truth/` — what the checklist check compares against: the ground-truth checklist per case (`northbridge-v-caldera.json`). Never part of the case, never seen by the agent or Muse Code.
- `world/` — the simulated outside world: withheld follow-up documents and `release.py`.
- `solutions/` — `01_session1/` and `02_session2/` snapshots.
- `ui/` — the Agent Console: start runs, watch each turn, see the agent's checklist and how each item is proven, release evidence, sign off. Pre-built; outside Muse Code's workspace.
