# Ground truth

What the checklist check compares the agent's checklist against. It lives outside `agent/` and outside the case, so neither Muse Code nor the agent's model sees it.

- `<case folder name>.json`: the ground-truth checklist for a case, i.e. the questions an investigation of that case must cover. `load_reference` in `agent/verification/verify_checklist.py` loads it by the case folder's name, and that file's `run_verification` asks Muse Spark which items the agent's checklist covers. The agent only gets pass/fail and feedback on what kind of question is missing; the console also shows the score. A case with no file here skips the checklist check.

To add a ground truth for a new case `cases/my-case/`, write `my-case.json`:

```json
{"items": [{"id": "short_id", "question": "What must be established?"}]}
```

`GROUND_TRUTH_DIR` in the environment overrides this folder's location (default: `../ground_truth`, relative to `agent/`).
