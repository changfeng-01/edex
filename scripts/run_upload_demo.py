from __future__ import annotations

import importlib
import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:5173"


def main() -> int:
    repo_root = Path.cwd()
    if not _looks_like_repo_root(repo_root):
        print("Run this script from the repository root: python scripts/run_upload_demo.py", file=sys.stderr)
        return 1

    if not _can_import_upload_app():
        print(
            "Cannot import goa_eval.web.app. Install the package first, for example: python -m pip install -e \".[test]\"",
            file=sys.stderr,
        )
        return 1

    frontend_dir = repo_root / "frontend"
    package_json = frontend_dir / "package.json"
    node_modules = frontend_dir / "node_modules"
    if not package_json.exists():
        print("frontend/package.json was not found. Run this script from the repository root.", file=sys.stderr)
        return 1
    if not node_modules.exists():
        print("frontend/node_modules was not found. Run 'npm install' in frontend/ first; this script will not install packages.", file=sys.stderr)
        return 1

    backend = _start_backend(repo_root)
    frontend = _start_frontend(frontend_dir)
    processes = [backend, frontend]

    print("")
    print("CircuitPilot Upload-to-Dashboard demo is starting.")
    print(f"Backend:  {BACKEND_URL}")
    print(f"Frontend: {FRONTEND_URL}")
    print("Open the page, then click 'Run Built-in Demo' or upload waveform.csv / params.yaml.")
    print("Press Ctrl+C to stop both services.")
    print("")

    try:
        time.sleep(2)
        webbrowser.open(FRONTEND_URL)
        while True:
            for process in processes:
                if process.poll() is not None:
                    _terminate_all(processes)
                    print(f"Process exited early with code {process.returncode}.", file=sys.stderr)
                    return process.returncode or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping demo services...")
        _terminate_all(processes)
        return 0


def _looks_like_repo_root(path: Path) -> bool:
    return (path / "pyproject.toml").exists() and (path / "src" / "goa_eval").is_dir() and (path / "frontend").is_dir()


def _can_import_upload_app() -> bool:
    try:
        importlib.import_module("goa_eval.web.app")
    except Exception as exc:
        print(f"Import check failed: {exc}", file=sys.stderr)
        return False
    return True


def _start_backend(repo_root: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "goa_eval.web.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=repo_root,
    )


def _start_frontend(frontend_dir: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["VITE_API_BASE_URL"] = BACKEND_URL
    return subprocess.Popen(["npm", "run", "dev"], cwd=frontend_dir, env=env)


def _terminate_all(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            _terminate(process)
    deadline = time.monotonic() + 5
    for process in processes:
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
    for process in processes:
        if process.poll() is None:
            process.kill()


def _terminate(process: subprocess.Popen) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    raise SystemExit(main())
