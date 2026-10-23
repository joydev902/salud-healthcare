"""Cross-platform task runner for the monorepo (no make/bash required).

    python run.py            # same as `dev`
    python run.py dev        # setup if needed, migrate, seed, run API :8000 + UI :5173
    python run.py setup      # create backend venv, install backend + frontend deps
    python run.py lint       # ruff check + ruff format --check, oxlint, prettier --check, tsc
    python run.py format     # ruff --fix + ruff format, prettier --write
    python run.py test       # backend pytest
    python run.py bench      # load ~200k synthetic rows into salud_mra_bench, write docs/performance.md
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
VENV = BACKEND / ".venv"
BIN = VENV / ("Scripts" if os.name == "nt" else "bin")
PY = BIN / ("python.exe" if os.name == "nt" else "python")
NPM = shutil.which("npm") or "npm"


def step(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


def run(cmd: list, cwd: Path) -> int:
    print(f"$ {' '.join(map(str, cmd))}", flush=True)
    return subprocess.call(cmd, cwd=cwd)


def check(cmd: list, cwd: Path) -> None:
    if run(cmd, cwd) != 0:
        sys.exit(1)


def setup(force: bool = False) -> None:
    if force or not PY.exists():
        step("Backend: virtualenv + dependencies")
        if not PY.exists():
            venv.create(VENV, with_pip=True)
        check([PY, "-m", "pip", "install", "-e", ".[dev]"], BACKEND)
    if force or not (FRONTEND / "node_modules").exists():
        step("Frontend: npm install")
        check([NPM, "install"], FRONTEND)


def dev() -> None:
    setup()
    step("Applying database migrations")
    check([PY, "-m", "alembic", "upgrade", "head"], BACKEND)
    step("Seeding demo accounts (idempotent)")
    check([PY, "-m", "app.seed"], BACKEND)

    step("API http://127.0.0.1:8000/docs  |  UI http://127.0.0.1:5173")
    # Ctrl+C reaches the API supervisor; when it exits we stop Vite too. Vite runs in its
    # own process group so stray console CTRL+C events cannot kill it on its own.
    signal.signal(signal.SIGINT, lambda *_: None)
    api = subprocess.Popen(
        [PY, "-m", "watchfiles", "--filter", "python", "app.devserver.serve", "app"],
        cwd=BACKEND,
    )
    ui = subprocess.Popen(
        [NPM, "run", "dev"],
        cwd=FRONTEND,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    try:
        while api.poll() is None and ui.poll() is None:
            time.sleep(0.5)
    finally:
        for proc in (ui, api):
            stop_tree(proc)


def stop_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.call(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        proc.terminate()


def lint() -> None:
    setup()
    checks = [
        ("ruff check", [PY, "-m", "ruff", "check", "."], BACKEND),
        ("ruff format --check", [PY, "-m", "ruff", "format", "--check", "."], BACKEND),
        ("oxlint", [NPM, "run", "lint"], FRONTEND),
        ("prettier --check", [NPM, "run", "format:check"], FRONTEND),
        ("tsc", [NPM, "run", "typecheck"], FRONTEND),
    ]
    failed = []
    for name, cmd, cwd in checks:
        step(name)
        if run(cmd, cwd) != 0:
            failed.append(name)
    if failed:
        print(f"\nFAILED: {', '.join(failed)}")
        sys.exit(1)
    print("\nAll lint checks passed.")


def fmt() -> None:
    setup()
    steps = [
        ("ruff format", [PY, "-m", "ruff", "format", "."], BACKEND),
        ("ruff check --fix", [PY, "-m", "ruff", "check", "--fix", "."], BACKEND),
        ("prettier --write", [NPM, "run", "format"], FRONTEND),
    ]
    failed = []
    for name, cmd, cwd in steps:
        step(name)
        if run(cmd, cwd) != 0:
            failed.append(name)
    if failed:
        print(f"\nNeeds manual fixes: {', '.join(failed)}")
        sys.exit(1)


def test() -> None:
    setup()
    step("Backend tests")
    check([PY, "-m", "pytest"], BACKEND)


def bench() -> None:
    setup()
    step("Benchmark: synthetic data in salud_mra_bench, report in docs/performance.md")
    check([PY, "-m", "scripts.benchmark"], BACKEND)


COMMANDS = {"dev": dev, "lint": lint, "format": fmt, "test": test, "bench": bench}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("command", nargs="?", default="dev", choices=[*COMMANDS, "setup"])
    args = parser.parse_args()
    if args.command == "setup":
        setup(force=True)
    else:
        COMMANDS[args.command]()


if __name__ == "__main__":
    main()
