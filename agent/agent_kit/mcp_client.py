"""The agent loop's view of the tools, served by mcp_server over streamable HTTP.

    mcp_client.definitions(root, run_id)   # the tools to offer the model in this run
    result = mcp_client.run(root, run_id, call)  # run the tool the model chose
    result.get("status", "running")        # "running", or why the run must stop

definitions() and run() match what agent_kit.tools used to offer: same OpenAI
function definitions (the internal run_id the server needs is stripped before the
model sees it, and injected on every call), same results and error shapes.

The server is expected at MCP_SERVER_URL (default http://127.0.0.1:8000/mcp). When
it is not reachable on a loopback address, it is started as a subprocess with the
run's root and stopped when this process exits; point MCP_SERVER_URL at a running
server to share one instead.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from mcp_server.server import HEALTH_PATH
from mcp_server.tools import names
from agent_kit.settings import mcp_server_url as configured_url

from .progress import load_progress

STARTUP_TIMEOUT_SECONDS = 15
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
AGENT_DIR = Path(__file__).resolve().parents[1]

_tool_list_cache: dict[str, list] = {}
_server_processes: dict[str, subprocess.Popen] = {}


def definitions(root: Path, run_id: str) -> list:
    """The tool definitions to offer the model in this run."""
    ensure_server(root)
    verification = bool(load_progress(root, run_id).get("verification"))
    offered = {tool["name"]: tool for tool in _list_tools()}
    return [
        {
            "type": "function",
            "name": name,
            "description": offered[name]["description"],
            "parameters": _model_schema(offered[name]["inputSchema"]),
        }
        for name in names(verification)
    ]


def run(root: Path, run_id: str, call: Any) -> dict:
    """Run the tool the model chose (an item of response.output, or the same as a dict)."""
    name, raw = _field(call, "name"), _field(call, "arguments") or "{}"
    try:
        args = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (TypeError, ValueError) as error:
        return {"error": f"tool arguments are not valid JSON: {error}"}
    if not isinstance(args, dict):
        return {"error": "tool arguments must be a JSON object"}
    root = Path(root)
    verification = bool(load_progress(root, run_id).get("verification"))
    if name not in names(verification):
        return {"error": f"unknown tool: {name!r}"}
    ensure_server(root)
    return _call_tool(configured_url(), name, dict(args, run_id=run_id))


def ensure_server(root: Path) -> None:
    """Start the MCP tool server for `root` when it is not already reachable."""
    url = configured_url()
    if _healthy(url):
        return
    host, port = _host_port(url)
    if host not in LOOPBACK_HOSTS:
        raise RuntimeError(f"MCP tool server at {url} is not reachable")
    if url in _server_processes and _server_processes[url].poll() is None:
        raise RuntimeError(f"MCP tool server at {url} is not reachable")
    log = Path(root) / "workspace/mcp_server.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    pythonpath = str(AGENT_DIR)
    if os.environ.get("PYTHONPATH"):
        pythonpath += os.pathsep + os.environ["PYTHONPATH"]
    with open(log, "a") as handle:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "mcp_server",
                "--host",
                host,
                "--port",
                str(port),
                "--root",
                str(root),
            ],
            cwd=str(root),
            env=dict(os.environ, PYTHONPATH=pythonpath),
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
    _server_processes[url] = process
    atexit.register(_stop_server, url)
    try:
        _wait_healthy(url, process)
    except Exception:
        _stop_server(url)
        raise
    print(f"MCP tool server started at {url} (log: {log})", flush=True)


def _stop_server(url: str) -> None:
    process = _server_processes.pop(url, None)
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def _healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(_health_url(url), timeout=1) as response:
            return response.status == 200
    except (OSError, ValueError):
        return False


def _wait_healthy(url: str, process: subprocess.Popen) -> None:
    import time

    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"MCP tool server exited (code {process.returncode}); see workspace/mcp_server.log"
            )
        if _healthy(url):
            return
        time.sleep(0.2)
    raise RuntimeError(f"MCP tool server at {url} did not start in time")


def _health_url(url: str) -> str:
    base = url[:-len("/mcp")] if url.rstrip("/").endswith("/mcp") else url.rstrip("/")
    return base + HEALTH_PATH


def _host_port(url: str) -> tuple[str, int]:
    parsed = urllib.parse.urlparse(url)
    if not parsed.hostname or not parsed.port:
        raise RuntimeError(f"MCP_SERVER_URL must be a full URL with a port: {url!r}")
    return parsed.hostname, parsed.port


def _model_schema(input_schema: dict) -> dict:
    """The MCP inputSchema as the model sees it: without the internal run_id."""
    schema = json.loads(json.dumps(input_schema))
    schema.get("properties", {}).pop("run_id", None)
    if "run_id" in schema.get("required", []):
        schema["required"] = [r for r in schema["required"] if r != "run_id"]
    return schema


def _list_tools() -> list:
    url = configured_url()
    if url not in _tool_list_cache:
        _tool_list_cache[url] = asyncio.run(_alist_tools(url))
    return _tool_list_cache[url]


async def _alist_tools(url: str) -> list:
    async with streamable_http_client(url) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema,
                }
                for tool in result.tools
            ]


def _call_tool(url: str, name: str, args: dict) -> dict:
    return asyncio.run(_acall_tool(url, name, args))


async def _acall_tool(url: str, name: str, args: dict) -> dict:
    async with streamable_http_client(url) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, args)
            if result.structuredContent:
                return dict(result.structuredContent)
            text = "\n".join(
                block.text for block in result.content or [] if block.type == "text"
            )
            try:
                parsed = json.loads(text) if text else {}
            except ValueError:
                parsed = {}
            if isinstance(parsed, dict) and parsed:
                return parsed
            return {"error": text or "empty tool result"}


def _field(call: Any, key: str) -> Any:
    return call.get(key) if isinstance(call, dict) else getattr(call, key, None)
