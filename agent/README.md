# Legal case-investigation agent

An agent that investigates a legal case from its documents — PDFs, scans, and photos — using the Meta Model API. It drafts a checklist of what must be proven, plans, records what it can prove in a case-management system, escalates to a person when it cannot prove something, and files a memo for attorney sign-off.

The case is a folder outside this directory, named by `CASE_DIR` in `.env`: an `objective.md` and a `documents/` folder of PDFs and images, nothing else (default: `../cases/northbridge-v-caldera`, a fictional dispute over a failed ERP go-live, 21 documents).

## Quick start

```bash
cp .env.example .env      # add MODEL_API_KEY; CASE_DIR names the case
./helper setup            # creates .venv (OpenAI Python SDK), copies the case's documents into the inbox, checks the key
```

The agent talks to the Meta Model API with the official OpenAI Python SDK (`base_url=https://api.meta.ai/v1`). `./helper` runs everything with `.venv/bin/python`.

Documents are read through the Files API, up to 4 at a time in parallel.

## Commands

```bash
./helper setup                         # reset the inbox to the case's documents
CASE_DIR=../cases/other ./helper setup # work on a different case
./helper test [--verification]         # offline tests; never call the live API
./helper run --turns 30                # run the agent (starts the MCP tool server on its own)
./helper run --resume RUN_ID --turns 15
./helper review RUN_ID --approve | --reject --notes "..." | --answer R1 --notes "..."
./helper verify RUN_ID --memo | --checklist   # run the verification checks on a finished run
./helper branch RUN_ID                 # continue a run from its checklist with verification on
./helper reset [--clear-runs]
```

## Repository map

- `legal_agent/` — the agent you build: the agentic loop (`loop.py`), and `system_instructions.md`, how it works any case (sent as its system prompt every turn; edit it to change how the agent works).
- `verification/` — the verification layer (`VERIFICATION=on`), every check in one place: one file per check, each with `run_verification(ctx, work)`: `verify_checklist.py` and `verify_memo.py` you build, `verify_claims.py` and `verify_evidence_request.py` are pre-built. See `VERIFICATION.md`; escalation and resume in `ESCALATION_RULES.md`.
- `mcp_server/` — the agent's tools as an MCP server over streamable HTTP (`./helper mcp-server`; the loop starts it on its own): `tools/` — one file per tool: what the model sees and what happens when it calls it;
- `agent_kit/` — pre-built plumbing:
  - `mcp_client.py` — the loop's view of the tools: `definitions()` and `run()` over the MCP server;
  - `progress.py` — a run on disk (`new_run`, `save_progress`, `load_progress`), `resume` after a person acts, and `branch`;
  - `case_record.py` — the simulated case-management system the agent acts on;
  - `document_text.py` — each document's saved text, the source of truth every quote is checked against;
  - `client.py` — the OpenAI client for the Meta Model API; `settings.py` — the `.env` settings.
- `tests/` — offline tests and the offline Model API they use (`fake_model.py`).
- `workspace/inbox/` — documents the agent can see. `workspace/runs/` — each run's saved progress. `workspace/case_records/` — case records. `workspace/cache/` — extracted text.

When the agent escalates for missing evidence, the run stops; once new documents are released into the inbox, resume the same run.
