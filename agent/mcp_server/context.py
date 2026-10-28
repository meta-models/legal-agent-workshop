"""What a tool gets besides its arguments, and the server's shared state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_kit.case_record import CaseRecord


@dataclass
class Context:
    """What a tool gets besides its arguments."""

    client: Any  # OpenAI (or the offline test double)
    root: Path
    run_id: str
    case: CaseRecord
    verification: bool


@dataclass
class State:
    """Shared server state, set once at startup (or per test, by the harness)."""

    root: Path = field(default_factory=lambda: Path.cwd())
    test_client: Any = None  # when set, tools use it instead of a real client
    _client: Any = None

    @property
    def client(self) -> Any:
        if self.test_client is not None:
            return self.test_client
        if self._client is None:
            from agent_kit.client import make_client

            self._client = make_client()
        return self._client


state = State()
