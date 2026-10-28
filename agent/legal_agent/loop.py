"""The Legal Agent: the agentic loop.

run_agent works the case; resume_run continues a run that stopped.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import OpenAI

from agent_kit import mcp_client, progress
from agent_kit.settings import case_dir, model

INSTRUCTIONS_PATH = Path(__file__).with_name("system_instructions.md")
NUDGE = "Call exactly one tool per turn. Never answer in plain text."
LAST_TURN = (
    "This is your last turn. File the memo now with submit_memo "
    "using what you have."
)


def run_agent(*, root: Path, client: OpenAI, turns: int = 30) -> dict:
    root = Path(root)
    instructions = INSTRUCTIONS_PATH.read_text()
    objective = (case_dir(root) / "objective.md").read_text()
    run_id = progress.new_run(root, instructions=instructions, objective=objective)
    messages: list = [{"role": "user", "content": objective}]
    return _loop(root, client, run_id, messages, instructions, turns)


def resume_run(*, root: Path, run_id: str, client: OpenAI, turns: int = 15) -> dict:
    root = Path(root)
    saved = progress.load_progress(root, run_id)
    step = progress.resume(root, run_id)
    if step["message"] is None:
        return {
            "run_id": run_id,
            "status": step["status"],
            "turn": saved["turn"],
            "note": step["note"],
        }
    messages = list(saved["messages"])
    messages.append({"role": "user", "content": step["message"]})
    instructions = (_run_dir(root, run_id) / "instructions.md").read_text()
    return _loop(root, client, run_id, messages, instructions, turns)


def _loop(
    root: Path,
    client: OpenAI,
    run_id: str,
    messages: list,
    instructions: str,
    turns: int,
) -> dict:
    for i in range(turns):
        if i == turns - 1:
            messages.append({"role": "user", "content": LAST_TURN})
        try:
            response = client.responses.create(
                model=model(),
                instructions=instructions,
                input=messages,
                tools=mcp_client.definitions(root, run_id),
                parallel_tool_calls=False,
            )
        except Exception as error:
            progress.save_progress(root, run_id, messages, status="paused")
            saved = progress.load_progress(root, run_id)
            return {
                "run_id": run_id,
                "status": "paused",
                "turn": saved["turn"],
                "note": str(error) or type(error).__name__,
            }
        output = [_plain(item) for item in response.output]
        messages.extend(output)
        call = next(
            (
                m
                for m in output
                if isinstance(m, dict) and m.get("type") == "function_call"
            ),
            None,
        )
        if call is None:
            messages.append({"role": "user", "content": NUDGE})
            progress.save_progress(root, run_id, messages, response, status="running")
            continue
        result = mcp_client.run(root, run_id, call)
        messages.append(
            {
                "type": "function_call_output",
                "call_id": call.get("call_id"),
                "output": json.dumps(result),
            }
        )
        status = (
            result.get("status", "running")
            if isinstance(result, dict)
            else "running"
        )
        progress.save_progress(root, run_id, messages, response, status=status)
        if status != "running":
            saved = progress.load_progress(root, run_id)
            return {"run_id": run_id, "status": status, "turn": saved["turn"]}
    progress.save_progress(root, run_id, messages, status="paused")
    saved = progress.load_progress(root, run_id)
    return {
        "run_id": run_id,
        "status": "paused",
        "turn": saved["turn"],
        "note": "turn limit reached",
    }


def _run_dir(root: Path, run_id: str) -> Path:
    return Path(root) / "workspace/runs" / run_id


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", exclude_none=True)
    return value
