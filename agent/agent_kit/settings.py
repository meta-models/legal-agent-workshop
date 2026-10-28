"""Run settings read from the environment (./helper loads .env)."""

from __future__ import annotations

import os
from pathlib import Path

_TRUE = {"on", "1", "true", "yes"}


def model() -> str:
    """The model the agent talks to (MODEL_API_MODEL, default muse-spark-1.3)."""
    return os.environ.get("MODEL_API_MODEL") or "muse-spark-1.3"


def sam_model() -> str:
    """The segmentation model check_signatures uses (SAM_MODEL, default sam-3.1)."""
    return os.environ.get("SAM_MODEL") or "sam-3.1"


def verification_enabled() -> bool:
    """VERIFICATION=on: new runs get the verification layer (agent/verification/): the
    checks run at fixed points, three more tools, escalation, and attorney sign-off."""
    return os.environ.get("VERIFICATION", "off").strip().lower() in _TRUE


def mcp_port() -> int:
    """The MCP tool server's port (MCP_PORT, default 8000)."""
    return int(os.environ.get("MCP_PORT") or 8000)


def mcp_server_url() -> str:
    """The MCP tool server endpoint (MCP_SERVER_URL, default http://127.0.0.1:<port>/mcp)."""
    return os.environ.get("MCP_SERVER_URL") or f"http://127.0.0.1:{mcp_port()}/mcp"


def case_dir(root: Path) -> Path:
    """The case folder (CASE_DIR, absolute or relative to the agent folder): objective.md and documents/."""
    value = os.environ.get("CASE_DIR", "").strip()
    if not value:
        raise RuntimeError("CASE_DIR is not set: point it at a case folder in .env")
    path = Path(value).expanduser()
    return path if path.is_absolute() else (Path(root) / path).resolve()
