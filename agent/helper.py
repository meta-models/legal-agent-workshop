#!/usr/bin/env python3
"""The ./helper commands in Python, for Windows (and anywhere bash isn't handy).

    python helper.py setup | test [--verification] | run [--turns N] [--resume RUN_ID]
                     verify RUN_ID --memo|--checklist | branch RUN_ID | review ... | reset | describe

Same behaviour as ./helper: commands run with the agent's own .venv Python, with .env
loaded (CASE_DIR set in the environment wins over .env), in UTF-8 mode.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

AGENT = Path(__file__).resolve().parent
USAGE = """Usage: python helper.py COMMAND
  setup                                  create .venv, copy the case's documents, check MODEL_API_KEY
  test [--verification]                  offline tests (no API calls)
  run [--turns N] [--resume RUN_ID]      run the agent, or continue a run
  verify RUN_ID --memo | --checklist     run the verification checks on a finished run
  branch RUN_ID                          continue a run from its checklist with verification on
  review RUN_ID --approve | --reject --notes "..." | --answer R1 --notes "..."
  reset [--clear-runs]                   reset the inbox to the case's documents
  describe                               what the agent gets (JSON; used by the console)"""


def venv_python() -> Path | None:
    for candidate in (".venv/Scripts/python.exe", ".venv/bin/python"):
        if (AGENT / candidate).is_file():
            return AGENT / candidate
    return None


def python() -> str:
    if os.environ.get("PYTHON"):
        return os.environ["PYTHON"]
    found = venv_python()
    return str(found) if found else sys.executable


def load_env(env: dict) -> dict:
    """KEY=VALUE lines of .env; comments and malformed lines are skipped."""
    case_dir = env.get("CASE_DIR", "")
    path = AGENT / ".env"
    if path.is_file():
        for number, line in enumerate(
            path.read_text(encoding="utf-8-sig").splitlines(), 1
        ):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                print(f".env line {number} is not KEY=VALUE; skipped", file=sys.stderr)
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("\"'")
    if case_dir:
        env["CASE_DIR"] = case_dir
    return env


def windows_ca_bundle() -> Path | None:
    """certifi's CAs plus the Windows trusted roots, so HTTPS works behind antivirus or
    proxies that re-sign traffic (Norton, corporate proxies). The SDK honours SSL_CERT_FILE."""
    import ssl

    try:
        found = subprocess.run(
            [python(), "-c", "import certifi; print(certifi.where())"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        pems = [Path(found).read_text(encoding="utf-8")]
    except (OSError, subprocess.CalledProcessError):
        return None
    for store in ("ROOT", "CA"):
        for cert, encoding, _trust in ssl.enum_certificates(store):
            if encoding == "x509_asn":
                pems.append(ssl.DER_cert_to_PEM_cert(cert))
    path = AGENT / "workspace/cache/ca-bundle.pem"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(pems), encoding="utf-8")
    return path


def trust_windows_certificates(env: dict) -> None:
    if os.name == "nt" and "SSL_CERT_FILE" not in env:
        bundle = windows_ca_bundle()
        if bundle:
            env["SSL_CERT_FILE"] = str(bundle)


def call(argv: list, env: dict) -> None:
    code = subprocess.call([python()] + argv, cwd=AGENT, env=env)
    if code:
        sys.exit(code)


def main() -> None:
    command, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("help", [])
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    if command in ("run", "verify", "branch"):
        trust_windows_certificates(env)
    if command == "setup":
        if not (AGENT / ".env").is_file():
            (AGENT / ".env").write_bytes((AGENT / ".env.example").read_bytes())
        if venv_python() is None:
            subprocess.check_call([sys.executable, "-m", "venv", ".venv"], cwd=AGENT)
        pip = [str(venv_python()), "-m", "pip", "install", "--quiet"]
        subprocess.check_call(
            pip + ["--disable-pip-version-check", "-r", "requirements.txt"], cwd=AGENT
        )
        load_env(env)
        trust_windows_certificates(env)
        call(["scripts/reset_case.py"], env)
        call(["scripts/preflight.py", "--expect-release", "initial", "--check-key"], env)
    elif command == "reset":
        call(["scripts/reset_case.py"] + args, load_env(env))
    elif command == "run":
        call(["-m", "legal_agent"] + args, load_env(env))
    elif command == "review":
        call(["scripts/review.py"] + args, env)
    elif command in ("describe", "verify", "branch"):
        call([f"scripts/{command}.py"] + args, load_env(env))
    elif command == "test":
        load_env(env)
        env["VERIFICATION"] = "on" if args[:1] == ["--verification"] else "off"
        call(["scripts/preflight.py", "--expect-release", "auto"], env)
        call(["-m", "unittest", "discover", "-s", "tests"], env)
    else:
        print(USAGE, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
