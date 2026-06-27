"""External simulator command-template adapter for PIA evolution."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def render_simulator_command(
    command_template: str,
    *,
    candidate_csv: Path,
    result_csv: Path,
    generation: int,
    output_dir: Path,
) -> str:
    return (
        command_template
        .replace("{candidate_csv}", str(candidate_csv))
        .replace("{result_csv}", str(result_csv))
        .replace("{candidate_id}", "")
        .replace("{generation}", str(generation))
        .replace("{output_dir}", str(output_dir))
    )


def run_external_simulator_command(
    command_template: str,
    *,
    candidate_csv: Path,
    result_csv: Path,
    generation: int,
    output_dir: Path,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Run an external simulator command and persist invocation evidence."""
    command = render_simulator_command(
        command_template,
        candidate_csv=candidate_csv,
        result_csv=result_csv,
        generation=generation,
        output_dir=output_dir,
    )
    invocation_path = output_dir / "simulator_invocation.json"
    stdout_path = output_dir / "simulator_stdout.txt"
    stderr_path = output_dir / "simulator_stderr.txt"

    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        invocation = {
            "command": command,
            "generation": generation,
            "candidate_csv": str(candidate_csv),
            "result_csv": str(result_csv),
            "output_dir": str(output_dir),
            "exit_code": None,
            "status": "timeout",
        }
        invocation_path.write_text(json.dumps(invocation, indent=2, ensure_ascii=False), encoding="utf-8")
        raise RuntimeError(f"external_command timed out: {command}") from exc

    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")
    invocation = {
        "command": command,
        "generation": generation,
        "candidate_csv": str(candidate_csv),
        "result_csv": str(result_csv),
        "output_dir": str(output_dir),
        "exit_code": proc.returncode,
        "status": "completed" if proc.returncode == 0 else "failed",
    }
    invocation_path.write_text(json.dumps(invocation, indent=2, ensure_ascii=False), encoding="utf-8")

    if proc.returncode != 0:
        raise RuntimeError(
            f"external_command failed with exit code {proc.returncode}: "
            f"stderr={(proc.stderr or '')[:500]}"
        )
    return invocation
