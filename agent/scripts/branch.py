#!/usr/bin/env python3
"""Continue a run from its checklist with the verification layer on.

./helper branch RUN_ID      # prints the new run's id; then ./helper run --resume NEW_RUN_ID

The new run keeps the conversation up to the agent's first set_checklist call, runs that
checklist through the checklist check, and stops. The original run is not changed.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_kit.progress import branch  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run_id")
    args = parser.parse_args()
    try:
        with contextlib.redirect_stdout(
            sys.stderr
        ):  # stdout carries only the JSON result
            new_id = branch(ROOT, args.run_id)
    except (RuntimeError, FileNotFoundError) as error:
        sys.exit(str(error))
    print(json.dumps({"run_id": new_id, "branched_from": args.run_id}, indent=2))
    print(f"Continue it with: ./helper run --resume {new_id}", file=sys.stderr)


if __name__ == "__main__":
    main()
