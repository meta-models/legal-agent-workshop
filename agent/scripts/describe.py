#!/usr/bin/env python3
"""What the agent gets when it starts: the case, its objective, the tools offered, and build
status (JSON). Used by the console.

./helper describe
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_kit.settings import case_dir, verification_enabled  # noqa: E402
from mcp_server import tools  # noqa: E402


def _has_ground_truth() -> bool:
    try:
        return (
            importlib.import_module("verification.verify_checklist")
            .reference_path(ROOT)
            .is_file()
        )
    except Exception:  # verify_checklist.py is broken mid-edit: report no ground truth
        return False


def built(path: Path) -> bool:
    return path.is_file() and "NotImplementedError(" not in path.read_text()


def main() -> None:
    verification = verification_enabled()
    case = case_dir(ROOT)
    objective = (case / "objective.md").read_text()
    title = next(
        (line[2:].strip() for line in objective.splitlines() if line.startswith("# ")),
        case.name,
    )
    inbox = ROOT / "workspace/inbox"
    print(
        json.dumps(
            {
                "verification": verification,
                "case": str(case),
                "title": title,
                "objective": objective,
                "ground_truth_checklist": _has_ground_truth(),
                "tools": [
                    {
                        "name": name,
                        "description": tools.DEFINITIONS[name]["description"],
                        "parameters": list(
                            tools.DEFINITIONS[name]["parameters"]["properties"]
                        ),
                    }
                    for name in tools.names(verification)
                ],
                "built": {
                    path: built(ROOT / path)
                    for path in (
                        "legal_agent/loop.py",
                        "verification/verify_checklist.py",
                        "verification/verify_memo.py",
                    )
                },
                "documents": len([p for p in inbox.glob("*") if p.is_file()])
                if inbox.exists()
                else 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
