"""The MCP server: all nine agent tools over streamable HTTP.

Run it with `python -m mcp_server` (or `./helper mcp-server`); the agent loop
(agent_kit/mcp_client.py) starts it on its own when it is not already running.

Each tool takes the arguments the model produced plus an internal `run_id` the
client injects (the model never sees it): the run id tells the server which run's
case record and verification flag to use. Tools are sync and sometimes slow
(analyze_document calls the Model API), so each call runs in a worker thread.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import anyio.to_thread
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool
from starlette.types import Receive, Scope, Send

from agent_kit import progress
from agent_kit.case_record import CaseRecord

from .context import Context, state
from .tools import BASE_TOOLS, DEFINITIONS, MODULES, VERIFIER_TOOLS, names

SERVER_NAME = "legal-agent-tools"
MCP_PATH = "/mcp"
HEALTH_PATH = "/health"

RUN_ID_SCHEMA = {
    "type": "string",
    "description": "Internal run id, filled by the harness; never set by the model.",
}

server = Server(SERVER_NAME)


def mcp_schema(definition: dict) -> dict:
    """A tool's DEFINITION parameters as an MCP inputSchema (plus internal run_id)."""
    schema = copy.deepcopy(definition["parameters"])
    schema.setdefault("properties", {})["run_id"] = RUN_ID_SCHEMA
    required = schema.setdefault("required", [])
    if "run_id" not in required:
        required.append("run_id")
    return schema


@server.list_tools()
async def _list_tools() -> list[Tool]:
    return [
        Tool(
            name=name,
            description=DEFINITIONS[name]["description"],
            inputSchema=mcp_schema(DEFINITIONS[name]),
        )
        for name in BASE_TOOLS + VERIFIER_TOOLS
    ]


@server.call_tool()
async def _call_tool(name: str, arguments: dict) -> dict:
    return await anyio.to_thread.run_sync(_dispatch, name, dict(arguments or {}))


def _dispatch(name: str, args: dict) -> dict:
    """Run one tool call (sync): build its Context from run_id and dispatch."""
    run_id = args.pop("run_id", "")
    root = state.root
    try:
        verification = bool(progress.load_progress(root, run_id).get("verification"))
    except (FileNotFoundError, OSError, ValueError):
        return {"error": f"no such run: {run_id}"}
    if name not in names(verification):
        return {"error": f"unknown tool: {name!r}"}
    ctx = Context(state.client, root, run_id, CaseRecord(root, run_id), verification)
    try:
        result = MODULES[name].run(ctx, args)
    except NotImplementedError as error:  # a check that is not built yet: stop the run
        return {"error": str(error), "status": "paused"}
    except Exception as error:  # the model reads the error and tries again
        return {"error": str(error) or type(error).__name__}
    return result if isinstance(result, dict) else {"result": result}


def create_asgi_app() -> Any:
    """The ASGI app: streamable HTTP at /mcp, a health check at /health."""
    manager = StreamableHTTPSessionManager(app=server, stateless=True)

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            async with manager.run():
                while True:
                    message = await receive()
                    if message["type"] == "lifespan.startup":
                        await send({"type": "lifespan.startup.complete"})
                    elif message["type"] == "lifespan.shutdown":
                        await send({"type": "lifespan.shutdown.complete"})
                        return
            return
        if scope["type"] != "http":
            return
        if scope["path"] == HEALTH_PATH and scope["method"] == "GET":
            body = json.dumps(
                {"ok": True, "server": SERVER_NAME, "tools": len(DEFINITIONS)}
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await manager.handle_request(scope, receive, send)

    return app
