# Copyright (c) 2026 Steve Manzuik
# Licensed under FSL-1.1-ALv2. See LICENSE.

from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import subprocess

from app.models import Exercise, InjectOption


class ChaosExecutionError(RuntimeError):
    pass


def read_chaos_state(exercise: Exercise) -> dict[str, Any] | None:
    state_path = Path(exercise.package_path) / "chaos" / "state" / "state.json"
    try:
        return json.loads(state_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def run_chaos_inject(
    exercise: Exercise,
    inject: InjectOption,
    intensity: str = "medium",
) -> str:
    if inject.action_type != "chaos_script":
        raise ValueError("Inject is not a chaos action")

    action = inject.payload.get("action")
    if action:
        intensities = inject.payload.get("intensities", ["medium"])
        if intensity not in intensities:
            raise ValueError(f"Unsupported intensity: {intensity}")
        script = _safe_script_path(
            exercise,
            inject.script_name or "chaos_cli.py",
        )
        return _run_script(
            script,
            ["run", str(action), "--intensity", intensity],
        )

    if not inject.script_name:
        raise ValueError("Chaos inject does not define a script")
    script = _safe_script_path(exercise, inject.script_name)
    return _run_script(script, [])


def reset_chaos(exercise: Exercise, action: str | None = None) -> str:
    chaos_root = Path(exercise.package_path).resolve() / "chaos"
    cli = chaos_root / "chaos_cli.py"
    if cli.exists():
        arguments = ["reset"]
        if action:
            arguments.append(action)
        return _run_script(cli, arguments)

    legacy_reset = chaos_root / "reset_chaos.py"
    if legacy_reset.exists() and not action:
        return _run_script(legacy_reset, [])
    raise ChaosExecutionError("This exercise package does not support that reset")


def _safe_script_path(exercise: Exercise, script_name: str) -> Path:
    chaos_root = Path(exercise.package_path).resolve() / "chaos"
    script = (chaos_root / script_name).resolve()
    if script.parent != chaos_root or script.suffix != ".py":
        raise ValueError("Invalid chaos script path")
    if not script.is_file():
        raise ChaosExecutionError(f"Chaos script not found: {script.name}")
    return script


def _run_script(script: Path, arguments: list[str]) -> str:
    try:
        process = subprocess.run(
            ["python3", str(script), *arguments],
            cwd=str(script.parent),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ChaosExecutionError("Chaos action timed out after 15 seconds") from exc

    output = "\n".join(
        part.strip() for part in (process.stdout, process.stderr) if part.strip()
    )
    if process.returncode != 0:
        raise ChaosExecutionError(output or "Chaos action failed")
    return output or "Chaos action completed."
