#!/usr/bin/env python3
"""Agent Console: a pre-built UI to start, watch, and steer the workshop agent.

Standard library only. From the legal-agent-workshop folder:

    python3 ui/ui.py
    open http://127.0.0.1:8765

It finds the workshop automatically (the folder that contains ui/). Use
--workshop PATH only to point it at a different clone.

It reads each run's progress.json (agent/workspace/runs/<run>/, written by
agent_kit.progress) and case record (agent/workspace/case_records/), and acts only
through the workshop's own commands (./helper run, ./helper review, world/release.py).
Any agent participants build with Muse Code shows up here as long as it saves its
progress every turn; the console never imports it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

CONSOLE = Path(__file__).resolve().parent
DEFAULT_WORKSHOP = CONSOLE.parent  # ui/ sits at the root of legal-agent-workshop
MAX_TURNS = 200
# Windows: text in UTF-8 everywhere (files, pipes, and every ./helper command we start).
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
TEXT = {"text": True, "encoding": "utf-8", "errors": "replace"}


def helper(*args: str) -> list:
    """The argv for a ./helper command; on Windows, the Python port (agent/helper.py)."""
    if os.name == "nt":
        return [sys.executable, "helper.py", *args]
    return ["./helper", *args]


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_progress(run_dir: Path) -> dict:
    return read_json(run_dir / "progress.json") or {}


def _parse(value: Any) -> dict:
    try:
        out = json.loads(value) if isinstance(value, str) else value
    except ValueError:
        return {"result": value}
    return out if isinstance(out, dict) else {"result": out}


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(c.get("text", "")) for c in content if isinstance(c, dict)
        ).strip()
    return json.dumps(content)


def _saw(items: list) -> dict:
    """What the model saw on one turn, in a few lines."""
    counts: dict[str, int] = {}
    for item in items:
        kind = {
            "function_call_output": "tool results",
            "function_call": "earlier tool calls",
            "reasoning": "reasoning notes",
        }.get(item.get("type", ""))
        kind = kind or (
            "user messages" if item.get("role") == "user" else "model messages"
        )
        counts[kind] = counts.get(kind, 0) + 1
    last = items[-1] if items else {}
    return {
        "items": len(items),
        "counts": counts,
        "newest_observation": str(last.get("output", ""))[:900]
        if last.get("type") == "function_call_output"
        else "",
        "newest_message": _text(last.get("content"))[:600]
        if last.get("role") == "user"
        else "",
    }


def _epoch(stamp: str | None) -> float:
    try:
        return datetime.fromisoformat(stamp or "").timestamp()
    except ValueError:
        return 0.0


def build_events(  # noqa: C901
    progress: dict, case: dict | None, job: dict | None
) -> list:
    """The run as a list of events for the timeline, rebuilt from the saved conversation
    and the case record."""
    events: list = []
    if not progress:
        return events
    messages = progress.get("messages") or []
    case = case or {}
    requests = {r.get("id"): r for r in case.get("requests") or []}
    checks = list(case.get("checklist_checks") or [])

    def add(event_type: str, actor: str, stamp: Any, /, **payload: Any) -> None:
        events.append(
            {
                "event_type": event_type,
                "actor": actor,
                "timestamp": stamp,
                "payload": payload,
            }
        )

    def what_happened(n: int, stamp: Any, name: str, args: dict, result: dict) -> None:
        """Checks, escalations, and flags the case system recorded for this tool call."""
        if name == "set_checklist":
            draft = [
                str(i.get("id")) for i in args.get("items") or [] if isinstance(i, dict)
            ]
            check = next((c for c in checks if c.get("draft") == draft), None)
            if check is not None:
                checks.remove(check)
                add(
                    "verification",
                    "agent",
                    stamp,
                    turn=n,
                    check="checklist",
                    passed=bool(check.get("passed")),
                    score=check.get("score"),
                    feedback=check.get("feedback", ""),
                    accepted=bool(check.get("accepted")),
                    attempt=check.get("attempt"),
                )
        if name == "submit_memo" and result.get("problems"):
            which = result.get("check", "memo")
            if which == "claims":
                add("verification", "agent", stamp, turn=n, check="memo", passed=True)
            add(
                "verification",
                "agent",
                stamp,
                turn=n,
                check=which,
                passed=False,
                problems=result["problems"],
            )
        if result.get("filed") and result.get("status") == "awaiting_signoff":
            add("verification", "agent", stamp, turn=n, check="memo", passed=True)
            add("verification", "agent", stamp, turn=n, check="claims", passed=True)
            add(
                "escalation",
                "agent",
                stamp,
                turn=n,
                rule="memo_signoff",
                need="Attorney sign-off on the filed memo.",
            )
        if result.get("escalated"):
            request = requests.get(result.get("request"), {})
            add(
                "escalation",
                "agent",
                stamp,
                turn=n,
                rule=request.get("rule", ""),
                item=result.get("item"),
                need=result.get("need"),
            )
        if isinstance(result.get("flagged"), dict):
            add(
                "flag",
                "agent",
                stamp,
                turn=n,
                kind="privileged",
                document_id=result["flagged"].get("document_id"),
            )

    add(
        "run_started",
        "agent",
        progress.get("started"),
        verification=bool(progress.get("verification")),
    )
    branched_from = (progress.get("notes") or {}).get("branched_from")
    if branched_from:
        check = checks.pop(0) if checks else {}
        add(
            "branched",
            "agent",
            progress.get("started"),
            branched_from=branched_from,
            passed=bool(check.get("passed")) if check else None,
            score=check.get("score"),
            feedback=check.get("feedback", ""),
        )
    status, last_time = "running", progress.get("started")
    for index, entry in enumerate(progress.get("turns") or []):
        stamp = entry.get("time")
        if status != "running":
            add("run_started", "agent", stamp, resumed=True)
        n = entry.get("turn")
        if n is not None:
            saw, out, end = (
                entry.get("saw", 0),
                entry.get("output", 0),
                entry.get("end", 0),
            )
            add("model_request", "agent", stamp, turn=n, saw=_saw(messages[:saw]))
            add(
                "model_response",
                "model",
                stamp,
                turn=n,
                input_tokens=entry.get("input_tokens", 0),
                output_tokens=entry.get("output_tokens", 0),
            )
            call = next(
                (m for m in messages[saw:out] if m.get("type") == "function_call"),
                None,
            )
            if call is not None:
                name, args = call.get("name", ""), _parse(call.get("arguments") or "{}")
                add("tool_call", "agent", stamp, turn=n, tool_name=name, arguments=args)
                output = next(
                    (
                        m
                        for m in messages[out:end]
                        if m.get("type") == "function_call_output"
                        and m.get("call_id") == call.get("call_id")
                    ),
                    None,
                )
                if output is not None:
                    result = _parse(output.get("output"))
                    add(
                        "tool_result",
                        "tool",
                        stamp,
                        turn=n,
                        tool_name=name,
                        result=result,
                    )
                    what_happened(n, stamp, name, args, result)
            add("state_snapshot", "agent", stamp, turn=n, status=entry.get("status"))
        status, last_time = entry.get("status", "running"), stamp
        if status != "running" and not (branched_from and index == 0):
            add("run_finished", "agent", stamp, status=status)
    if job and (status == "running" or job.get("started", 0) > _epoch(last_time)):
        stamp = datetime.now(timezone.utc).isoformat()
        if status != "running":
            add("run_started", "agent", stamp, resumed=True)
        add(
            "model_request",
            "agent",
            stamp,
            turn=int(progress.get("turn") or 0) + 1,
            pending=True,
        )
    return events


def run_state(progress: dict, events: list) -> dict:
    """What the side panels show: status, turn, the latest plan, the documents read."""
    plan: list = []
    analyzed: list = []
    args: dict = {}
    for e in events:
        p = e["payload"]
        if e["event_type"] == "tool_call":
            args = p.get("arguments") or {}
        elif e["event_type"] == "tool_result":
            result = p.get("result") or {}
            if p.get("tool_name") == "update_plan" and isinstance(
                result.get("plan"), list
            ):
                plan = result["plan"]
            if p.get("tool_name") == "analyze_document" and "error" not in result:
                ids = args.get("document_ids") or []
                analyzed += [d for d in ids if d not in analyzed]
    return {
        **(progress.get("notes") or {}),
        "run_id": progress.get("run_id"),
        "verification": bool(progress.get("verification")),
        "model": progress.get("model"),
        "turn": progress.get("turn"),
        "status": progress.get("status"),
        "plan": plan,
        "analyzed_ids": analyzed,
    }


def metrics(events: list, case: dict | None) -> dict:
    m: dict[str, Any] = {
        "agent_turns": 0,
        "tool_calls": 0,
        "tokens": 0,
        "rejected": len((case or {}).get("rejected_facts") or []),
        "escalations": 0,
    }
    for e in events:
        k, p = e.get("event_type"), e.get("payload") or {}
        if k == "model_request" and not p.get("pending"):
            m["agent_turns"] += 1
        elif k == "model_response":
            m["tokens"] += int(p.get("input_tokens") or 0) + int(
                p.get("output_tokens") or 0
            )
        elif k == "tool_call":
            m["tool_calls"] += 1
        elif k in ("verification", "branched") and p.get("passed") is False:
            m["rejected"] += 1
        elif k == "escalation":
            m["escalations"] += 1
    return m


class Jobs:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.items: list = []

    def start(
        self, kind: str, argv: list, cwd: Path, runs: Path, run_id: str = ""
    ) -> dict:
        before = {p.name for p in runs.glob("run-*")} if runs.exists() else set()
        process = subprocess.Popen(
            argv, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **TEXT
        )
        job = {
            "id": len(self.items) + 1,
            "kind": kind,
            "argv": " ".join(argv),
            "run_id": run_id,
            "started": time.time(),
            "returncode": None,
            "log": "",
        }
        with self.lock:
            self.items.append(job)
        threading.Thread(target=self._pump, args=(job, process), daemon=True).start()
        if not run_id:
            threading.Thread(
                target=self._discover, args=(job, runs, before), daemon=True
            ).start()
        return job

    def _pump(self, job: dict, process) -> None:
        for line in process.stdout:
            with self.lock:
                job["log"] = (job["log"] + line)[-20000:]
        job["returncode"] = process.wait()

    def _discover(self, job: dict, runs: Path, before: set) -> None:
        while not job["run_id"]:
            fresh = (
                sorted(p.name for p in runs.glob("run-*") if p.name not in before)
                if runs.exists()
                else []
            )
            if fresh:
                job["run_id"] = fresh[-1]
                return
            if job["returncode"] is not None:
                return
            time.sleep(0.2)

    def snapshot(self) -> list:
        with self.lock:
            return [dict(j, running=j["returncode"] is None) for j in self.items]

    def active_for(self, run_id: str):
        return next(
            (
                j
                for j in reversed(self.snapshot())
                if j["run_id"] == run_id and j["running"]
            ),
            None,
        )

    def any_running(self) -> bool:
        return any(j["running"] for j in self.snapshot())


class Console:
    def __init__(self, workshop: Path | None) -> None:
        self.jobs = Jobs()
        self.workshop: Path | None = None
        if workshop:
            self.set_workshop(str(workshop))

    # ---- workshop ----
    def set_workshop(self, path: str) -> dict:
        root = Path(path).expanduser().resolve()
        if (root / "helper").is_file() and (root.parent / "world").is_dir():
            root = root.parent  # pointed at agent/
        if not (root / "agent/helper").is_file():
            raise RuntimeError(
                f"not a legal-agent-workshop folder (no agent/helper): {root}"
            )
        if self.jobs.any_running():
            raise RuntimeError("wait for the running agent to stop first")
        self.workshop = root
        return self.info()

    @property
    def agent(self) -> Path:
        if not self.workshop:
            raise RuntimeError("choose the legal-agent-workshop folder first")
        return self.workshop / "agent"

    @property
    def world(self) -> Path:
        return self.agent.parent / "world"

    @property
    def runs(self) -> Path:
        return self.agent / "workspace/runs"

    def _env(self) -> dict:
        env = {}
        path = self.agent / ".env"
        if path.is_file():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
        return env

    def case_dir(self) -> Path:
        """The case the agent works on (CASE_DIR in agent/.env, relative to agent/)."""
        value = self._env().get("CASE_DIR", "")
        path = Path(value).expanduser() if value else self.agent / "case"
        return path if path.is_absolute() else (self.agent / path).resolve()

    def _display_path(self, path: Path) -> str:
        """A path relative to the workshop folder when it is inside it (cases/xyz)."""
        if self.workshop is None:
            return str(path)
        try:
            return str(path.resolve().relative_to(self.workshop))
        except ValueError:
            return str(path)

    def cases(self) -> list:
        """Every folder under cases/ that has an objective.md, with its title."""
        folder = self.workshop / "cases" if self.workshop else None
        if not folder or not folder.is_dir():
            return []
        out = []
        for case in sorted(p for p in folder.iterdir() if p.is_dir()):
            objective = case / "objective.md"
            if not objective.is_file():
                continue
            title = next(
                (
                    line[2:].strip()
                    for line in objective.read_text(encoding="utf-8", errors="replace").splitlines()
                    if line.startswith("# ")
                ),
                case.name,
            )
            out.append(
                {"id": case.name, "path": self._display_path(case), "title": title}
            )
        return out

    def select_case(self, case_id: str) -> dict:
        """Point CASE_DIR in agent/.env at cases/<case_id> and re-seed the inbox."""
        if self.jobs.any_running():
            raise RuntimeError(
                "wait for the running agent to stop before switching cases"
            )
        if case_id not in {c["id"] for c in self.cases()}:
            raise FileNotFoundError(case_id)
        path = self.agent / ".env"
        lines = path.read_text(encoding="utf-8-sig").splitlines() if path.is_file() else []
        setting = f"CASE_DIR=../cases/{case_id}"
        for i, line in enumerate(lines):
            if line.split("=", 1)[0].strip() == "CASE_DIR":
                lines[i] = setting
                break
        else:
            lines.append(setting)
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(path)
        self._cmd(helper("reset"), self.agent)
        return self.info()

    def info(self) -> dict:
        if not self.workshop:
            return {"workshop": None, "jobs": []}
        env = self._env()
        return {
            "workshop": str(self.workshop),
            "case": self._display_path(self.case_dir()),
            "cases": self.cases(),
            "verification": env.get("VERIFICATION", "off").strip().lower()
            in ("on", "1", "true", "yes"),
            "api_key_configured": bool(env.get("MODEL_API_KEY")),
            "model": env.get("MODEL_API_MODEL", "muse-spark-1.3"),
            "agent_ready": self._agent_ready(),
            "jobs": self.jobs.snapshot()[-10:],
            "control": self.control(),
        }

    def _agent_ready(self) -> bool:
        loop = self.agent / "legal_agent/loop.py"
        return loop.is_file() and "is not implemented yet" not in loop.read_text(encoding="utf-8")

    # ---- reads ----
    def list_runs(self) -> list:
        if not self.workshop or not self.runs.exists():
            return []
        rows = []
        for run_dir in sorted(self.runs.glob("run-*"), reverse=True):
            progress = read_progress(run_dir)
            rows.append(
                {
                    "id": run_dir.name,
                    "status": "running"
                    if self.jobs.active_for(run_dir.name)
                    else progress.get("status", "unknown"),
                    "verification": bool(progress.get("verification")),
                    "turn": progress.get("turn"),
                    "started": progress.get("started"),
                }
            )
        return rows

    def run_detail(self, run_id: str) -> dict:
        run_dir = self._run_dir(run_id)
        progress = read_progress(run_dir)
        case = read_json(self.agent / "workspace/case_records" / f"{run_id}.json")
        job = self.jobs.active_for(run_id)
        paused = bool(job) and bool(
            self.control().get("waiting")
        )  # step mode, between turns
        events = build_events(progress, case, None if paused else job)
        instructions = run_dir / "instructions.md"
        return {
            "verification": read_json(run_dir / "verification.json") or [],
            "branched_from": (progress.get("notes") or {}).get("branched_from"),
            "error": (progress.get("notes") or {}).get("error")
            if progress.get("status") == "paused"
            else None,
            "id": run_id,
            "status": "running" if job else progress.get("status", "unknown"),
            "state": run_state(progress, events),
            "case": case,
            "events": events,
            "metrics": metrics(events, case),
            "instructions": instructions.read_text(encoding="utf-8")[:400]
            if instructions.is_file()
            else "",
            "job": job,
        }

    def page_image(self, doc: str, page: str) -> bytes:
        name = f"{doc}-p{int(page)}.png"
        if "/" in doc or "\\" in doc or ".." in doc:
            raise FileNotFoundError(doc)
        for folder in (
            self.agent / "workspace/inbox/pages",
            self.case_dir() / "documents/pages",
            self.world / "follow_up/pages",
        ):
            if (folder / name).is_file():
                return (folder / name).read_bytes()
        raise FileNotFoundError(name)

    def documents(self) -> dict:
        if not self.workshop:
            return {"visible": [], "withheld": 0}
        inbox = self.agent / "workspace/inbox"
        visible = (
            [
                {"id": path.stem, "file": path.name}
                for path in sorted(inbox.iterdir())
                if path.is_file()
                and path.suffix.lower() in {".pdf", ".jpg", ".jpeg", ".png"}
            ]
            if inbox.exists()
            else []
        )
        names = {d["id"] for d in visible}
        follow = self.world / "follow_up"
        withheld = (
            sum(
                1
                for p in follow.iterdir()
                if p.is_file()
                and p.suffix.lower() in {".pdf", ".jpg", ".png"}
                and p.stem not in names
            )
            if follow.exists()
            else 0
        )
        return {"visible": visible, "withheld": withheld}

    def describe(self) -> dict:
        out = subprocess.run(
            helper("describe"), cwd=self.agent, capture_output=True, **TEXT
        )
        if out.returncode:
            raise RuntimeError(
                (out.stderr or out.stdout).strip()[-400:] or "describe failed"
            )
        return json.loads(out.stdout)

    # ---- step mode (workspace/control.json, read by agent_kit.progress after each saved turn) ----
    def control(self) -> dict:
        return read_json(self.agent / "workspace/control.json") or {
            "step": False,
            "credits": 0,
            "waiting": False,
        }

    def set_control(self, change: dict) -> dict:
        control = self.control()
        if "step" in change:
            control["step"] = bool(change["step"])
            if not control["step"]:
                control["waiting"] = False
        if change.get("next"):
            control["credits"] = int(control.get("credits", 0)) + 1
        path = self.agent / "workspace/control.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(control))
        tmp.replace(path)
        return control

    # ---- actions ----
    def start_run(self, turns: int, step: bool = False) -> dict:
        if not self.jobs.any_running():
            self._reset_control(step)
        return self._launch("run", turns, "")

    def resume_run(self, run_id: str, turns: int, step: bool | None = None) -> dict:
        self._run_dir(run_id)
        if not self.jobs.any_running():
            self._reset_control(bool(step))
        return self._launch("resume", turns, run_id)

    def _reset_control(self, step: bool) -> None:
        """A new run starts with no saved 'Next turn' clicks: the first turn always runs."""
        self.set_control({"step": step})
        control = dict(self.control(), credits=0, waiting=False)
        path = self.agent / "workspace/control.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(control))
        tmp.replace(path)

    def _launch(self, kind: str, turns: int, run_id: str) -> dict:
        if self.jobs.any_running():
            raise RuntimeError("an agent run is already in progress")
        turns = max(1, min(int(turns), MAX_TURNS))
        argv = helper("run", "--turns", str(turns))
        if run_id:
            argv += ["--resume", run_id]
        return self.jobs.start(kind, argv, self.agent, self.runs, run_id)

    def _cmd(self, argv: list, cwd: Path) -> dict:
        out = subprocess.run(argv, cwd=cwd, capture_output=True, **TEXT)
        if out.returncode:
            raise RuntimeError((out.stderr or out.stdout).strip()[-800:])
        return {"message": (out.stdout + out.stderr).strip()[-800:]}

    def release(self) -> dict:
        return self._cmd(
            [
                sys.executable,
                str(self.world / "release.py"),
                "--agent",
                str(self.agent),
            ],
            self.agent.parent,
        )

    def review(
        self, run_id: str, decision: str, notes: str, request_id: str = ""
    ) -> dict:
        self._run_dir(run_id)
        argv = helper("review", run_id)
        if decision == "answer":
            argv += ["--answer", request_id]
        else:
            argv += ["--approve" if decision == "approve" else "--reject"]
        if notes:
            argv += ["--notes", notes]
        return self._cmd(argv, self.agent)

    def verify(self, run_id: str, what: str) -> dict:
        """./helper verify RUN --memo | --checklist: the checks on a finished run's work."""
        self._run_dir(run_id)
        if what not in ("memo", "checklist"):
            raise RuntimeError("verify the memo or the checklist")
        out = subprocess.run(
            helper("verify", run_id, f"--{what}", "--json"),
            cwd=self.agent,
            capture_output=True,
            **TEXT,
        )
        if out.returncode:
            raise RuntimeError((out.stderr or out.stdout).strip()[-800:])
        return _json_result(out.stdout)

    def branch(self, run_id: str) -> dict:
        """./helper branch RUN: a new run, verification on, from the run's checklist turn."""
        self._run_dir(run_id)
        if self.jobs.any_running():
            raise RuntimeError("wait for the running agent to stop")
        out = subprocess.run(
            helper("branch", run_id),
            cwd=self.agent,
            capture_output=True,
            **TEXT,
        )
        if out.returncode:
            raise RuntimeError((out.stderr or out.stdout).strip()[-800:])
        return _json_result(out.stdout)

    def reset(self, clear_runs: bool) -> dict:
        if self.jobs.any_running():
            raise RuntimeError("stop the running agent before resetting")
        return self._cmd(
            helper("reset", *(["--clear-runs"] if clear_runs else [])), self.agent
        )

    def _run_dir(self, run_id: str) -> Path:
        if "/" in run_id or "\\" in run_id or ".." in run_id or not run_id.startswith("run-"):
            raise FileNotFoundError(run_id)
        run_dir = self.runs / run_id
        if not run_dir.is_dir():
            raise FileNotFoundError(run_id)
        return run_dir


def _json_result(stdout: str) -> dict:
    """The JSON object a ./helper command printed last (any progress lines before it are skipped)."""
    start = stdout.rfind("\n{")
    try:
        return json.loads(stdout[start + 1 :] if start >= 0 else stdout)
    except ValueError:
        raise RuntimeError(f"unexpected output: {stdout.strip()[-300:]}") from None


def make_handler(console: Console) -> type[BaseHTTPRequestHandler]:  # noqa: C901
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

        def _send(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: object, status: int = 200) -> None:
            self._send(status, json.dumps(payload).encode(), "application/json")

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(n)) if n else {}
            except ValueError:
                return {}

        def do_GET(self) -> None:
            url = urlparse(self.path)
            q = parse_qs(url.query)
            parts = [p for p in url.path.split("/") if p]
            try:
                if url.path in ("/", "/index.html"):
                    self._send(
                        200,
                        (CONSOLE / "index.html").read_bytes(),
                        "text/html; charset=utf-8",
                    )
                elif parts == ["api", "info"]:
                    self._json(console.info())
                elif parts == ["api", "runs"]:
                    self._json(console.list_runs())
                elif parts == ["api", "documents"]:
                    self._json(console.documents())
                elif parts == ["api", "describe"]:
                    self._json(console.describe())
                elif parts == ["api", "page"]:
                    self._send(
                        200,
                        console.page_image(
                            q.get("doc", [""])[0], q.get("page", ["1"])[0]
                        ),
                        "image/png",
                    )
                elif len(parts) == 3 and parts[:2] == ["api", "runs"]:
                    self._json(console.run_detail(parts[2]))
                else:
                    self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            except FileNotFoundError as error:
                self._json({"error": f"not found: {error}"}, HTTPStatus.NOT_FOUND)
            except RuntimeError as error:
                self._json({"error": str(error)}, HTTPStatus.CONFLICT)

        def do_POST(self) -> None:
            parts = [p for p in urlparse(self.path).path.split("/") if p]
            b = self._body()
            try:
                if parts == ["api", "workshop"]:
                    self._json(console.set_workshop(b.get("path", "")))
                elif parts == ["api", "case"]:
                    self._json(console.select_case(str(b.get("case", ""))))
                elif parts == ["api", "runs"]:
                    self._json(
                        console.start_run(b.get("turns", 30), bool(b.get("step")))
                    )
                elif (
                    len(parts) == 4
                    and parts[:2] == ["api", "runs"]
                    and parts[3] == "resume"
                ):
                    self._json(
                        console.resume_run(parts[2], b.get("turns", 15), b.get("step"))
                    )
                elif parts == ["api", "control"]:
                    self._json(console.set_control(b))
                elif (
                    len(parts) == 4
                    and parts[:2] == ["api", "runs"]
                    and parts[3] == "review"
                ):
                    self._json(
                        console.review(
                            parts[2],
                            b.get("decision", ""),
                            b.get("notes", ""),
                            b.get("request_id", ""),
                        )
                    )
                elif (
                    len(parts) == 4
                    and parts[:2] == ["api", "runs"]
                    and parts[3] == "verify"
                ):
                    self._json(console.verify(parts[2], str(b.get("what", ""))))
                elif (
                    len(parts) == 4
                    and parts[:2] == ["api", "runs"]
                    and parts[3] == "branch"
                ):
                    self._json(console.branch(parts[2]))
                elif parts == ["api", "release"]:
                    self._json(console.release())
                elif parts == ["api", "reset"]:
                    self._json(console.reset(bool(b.get("clear_runs"))))
                else:
                    self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            except FileNotFoundError as error:
                self._json({"error": f"not found: {error}"}, HTTPStatus.NOT_FOUND)
            except RuntimeError as error:
                self._json({"error": str(error)}, HTTPStatus.CONFLICT)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Console for the legal agent workshop"
    )
    parser.add_argument(
        "--workshop",
        type=Path,
        default=None,
        help="a different legal-agent-workshop folder (default: the one this ui/ folder is in)",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    workshop = args.workshop
    if workshop is None and (DEFAULT_WORKSHOP / "agent/helper").is_file():
        workshop = DEFAULT_WORKSHOP
    console = Console(workshop)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(console))
    print(
        f"Agent Console → http://{args.host}:{args.port}"
        + (
            f"  (workshop: {console.workshop})"
            if console.workshop
            else "  (choose the workshop folder in the UI)"
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
