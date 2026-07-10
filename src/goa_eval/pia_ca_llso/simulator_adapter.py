"""External simulator command-template adapter for PIA evolution."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Sequence


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


def render_simulator_argv(
    command_argv: Sequence[str],
    *,
    candidate_csv: Path,
    result_csv: Path,
    generation: int,
    output_dir: Path,
) -> list[str]:
    replacements = {
        "{candidate_csv}": str(candidate_csv),
        "{result_csv}": str(result_csv),
        "{candidate_id}": "",
        "{generation}": str(generation),
        "{output_dir}": str(output_dir),
    }
    rendered = []
    for argument in command_argv:
        value = str(argument)
        for placeholder, replacement in replacements.items():
            value = value.replace(placeholder, replacement)
        rendered.append(value)
    return rendered


def run_external_simulator_command(
    command_template: str | None,
    *,
    command_argv: Sequence[str] | None = None,
    candidate_csv: Path,
    result_csv: Path,
    generation: int,
    output_dir: Path,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Run an external simulator command and persist invocation evidence."""
    legacy_shell_command = command_argv is None
    command: str | list[str]
    if command_argv is not None:
        command = render_simulator_argv(
            command_argv,
            candidate_csv=candidate_csv,
            result_csv=result_csv,
            generation=generation,
            output_dir=output_dir,
        )
    elif command_template:
        command = render_simulator_command(
            command_template,
            candidate_csv=candidate_csv,
            result_csv=result_csv,
            generation=generation,
            output_dir=output_dir,
        )
    else:
        raise ValueError("external simulator command is required")
    invocation_path = output_dir / "simulator_invocation.json"
    stdout_path = output_dir / "simulator_stdout.txt"
    stderr_path = output_dir / "simulator_stderr.txt"

    try:
        proc = subprocess.run(
            command,
            shell=legacy_shell_command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=output_dir,
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
            "working_directory": str(output_dir),
            "executable": command[0] if isinstance(command, list) else None,
            "legacy_shell_command": legacy_shell_command,
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
        "working_directory": str(output_dir),
        "executable": command[0] if isinstance(command, list) else None,
        "legacy_shell_command": legacy_shell_command,
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
