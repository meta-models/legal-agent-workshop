# Solutions

Complete snapshots of `agent/` at each checkpoint. Outside Muse Code's workspace. `01_session1` runs with `VERIFICATION=off`, `02_session2` with `VERIFICATION=on`.

- `01_session1/` — end of Session 1 = start of Session 2: the agent (`legal_agent/loop.py`: the loop). It answers with an unverified memo; the two verification checks (`verification/verify_checklist.py`, `verification/verify_memo.py`) are still stubs.
- `02_session2/` — the same agent plus the two checks filled in. Everything else in the verification layer (escalation rule, claims check, the refusal limits, sign-off, resume, verify, branch) is pre-built in the kit.

## Catch up a stuck or late participant

Keeps `.env`, `.venv/`, and `workspace/` (runs, case records, cached text); replaces everything else.

```bash
# From the workshop root
rsync -a --delete --exclude .env --exclude .venv --exclude workspace solutions/01_session1/agent/ agent/
```

For the end of Session 2 use `solutions/02_session2/agent/` the same way. Runs started after `VERIFICATION=on` is set in `agent/.env` get the verification layer.

Without rsync: `find agent -mindepth 1 -maxdepth 1 ! -name .env ! -name .venv ! -name workspace -exec rm -rf {} +` then `cp -R solutions/01_session1/agent/. agent/` (this also copies `.env.example`; it does not touch `.env`).
