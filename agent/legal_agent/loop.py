"""The Legal Agent: the agentic loop. Not implemented yet.

run_agent works the case; resume_run continues a run that stopped. Build both: the
console starts runs with run_agent and continues them with resume_run.
"""

from __future__ import annotations

from pathlib import Path

from openai import OpenAI


def run_agent(*, root: Path, client: OpenAI, turns: int = 30) -> dict:
    raise NotImplementedError("run_agent is not implemented yet")


def resume_run(*, root: Path, run_id: str, client: OpenAI, turns: int = 15) -> dict:
    """Continue a stopped run from its saved progress. Build it together with run_agent:
    every Resume button in the console, and Approve and Reject at sign-off, call it.

    agent_kit.progress.resume(root, run_id) works out what happened while the run was
    stopped (more turns, a person's reply or new documents, the attorney's decision) and
    returns the message to send the model next, or None when there is nothing to continue.
    """
    raise NotImplementedError("resume_run is not implemented yet")
