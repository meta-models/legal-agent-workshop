"""Run the MCP tool server: python -m mcp_server [--host H] [--port P] [--root DIR]."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

from mcp_server.context import state  # noqa: E402
from mcp_server.server import HEALTH_PATH, MCP_PATH, create_asgi_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8000")))
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    state.root = Path(args.root).resolve()
    url = f"http://{args.host}:{args.port}{MCP_PATH}"
    print(f"MCP tool server at {url} (health: {HEALTH_PATH}) · root {state.root}", flush=True)
    uvicorn.run(create_asgi_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
