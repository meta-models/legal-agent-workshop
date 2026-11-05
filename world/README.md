# Simulated external world

Muse Code runs from `agent/` and must not read this directory.

- `follow_up/` — seven documents withheld at the start, with page images in `follow_up/pages/`.
- `release.py` — copies the follow-up documents and their page images into the agent's inbox (`agent/workspace/inbox`) after a run stops with `needs_input`: `python3 world/release.py`.
- `utils/` — the scripts that built the signature assets and page images (one-off utilities, not agent tools).
