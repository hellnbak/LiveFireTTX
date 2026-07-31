# Copyright (c) 2026 Steve Manzuik
# Licensed under FSL-1.1-ALv2. See LICENSE.

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import json
import subprocess

from app.models import Exercise, InjectOption


CONTROL_URL = "http://127.0.0.1:8090"


class ChaosExecutionError(RuntimeError):
    pass


class ChaosPreflightError(ChaosExecutionError):
    pass


def read_chaos_state(exercise: Exercise) -> dict[str, Any] | None:
    state_path = Path(exercise.package_path) / "chaos" / "state" / "state.json"
    try:
        state = json.loads(state_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return _effective_state_view(state)


def read_control_status(exercise: Exercise) -> dict[str, Any]:
    metadata = _control_metadata(exercise)
    if not metadata:
        return {
            "mode": "legacy",
            "reachable": None,
            "ready": True,
            "exercise_id": exercise.id,
        }
    try:
        status = _request_json(f"{CONTROL_URL}/health", timeout=0.75)
    except ChaosExecutionError as exc:
        return {
            "mode": "guarded",
            "reachable": False,
            "ready": False,
            "exercise_id": exercise.id,
            "error": str(exc),
            "target": {"reachable": False},
        }

    matches_exercise = status.get("exercise_id") == exercise.id
    return {
        **status,
        "mode": "guarded",
        "reachable": True,
        "ready": bool(status.get("ready") and matches_exercise),
        "matches_exercise": matches_exercise,
    }


def run_chaos_inject(
    exercise: Exercise,
    inject: InjectOption,
    intensity: str = "medium",
    duration_seconds: int = 300,
    guardrail_profile: str = "standard",
) -> str:
    if inject.action_type != "chaos_script":
        raise ValueError("Inject is not a chaos action")

    action = inject.payload.get("action")
    if action:
        _validate_option(inject, "intensities", intensity, "intensity")
        _validate_option(
            inject,
            "durations",
            duration_seconds,
            "duration",
        )
        guardrails = inject.payload.get("guardrail_profiles", {})
        if guardrails:
            if guardrail_profile not in guardrails:
                raise ValueError(f"Unsupported guardrail profile: {guardrail_profile}")
            status = read_control_status(exercise)
            if not status.get("reachable"):
                raise ChaosPreflightError(
                    "Guarded chaos controller is unavailable; deploy the generated lab"
                )
            if not status.get("matches_exercise"):
                raise ChaosPreflightError(
                    "The running chaos controller belongs to a different exercise"
                )
            if not status.get("ready"):
                raise ChaosPreflightError(
                    "Target preflight failed; validate the generated lab before applying chaos"
                )

            result = _request_json(
                f"{CONTROL_URL}/actions/{quote(str(action))}",
                {
                    "intensity": intensity,
                    "duration_seconds": int(duration_seconds),
                    **guardrails[guardrail_profile],
                },
            )
            result["guardrail_profile"] = guardrail_profile
            return json.dumps(result, indent=2, sort_keys=True)

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
    if _control_metadata(exercise):
        endpoint = "/reset"
        if action:
            endpoint += f"/{quote(action)}"
        result = _guarded_request(exercise, endpoint)
        return json.dumps(result, indent=2, sort_keys=True)

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


def emergency_stop(exercise: Exercise) -> str:
    if _control_metadata(exercise):
        result = _guarded_request(exercise, "/emergency-stop")
        return json.dumps(result, indent=2, sort_keys=True)
    return reset_chaos(exercise)


def _guarded_request(exercise: Exercise, endpoint: str) -> dict[str, Any]:
    status = read_control_status(exercise)
    if not status.get("reachable"):
        raise ChaosPreflightError("Guarded chaos controller is unavailable")
    if not status.get("matches_exercise"):
        raise ChaosPreflightError(
            "The running chaos controller belongs to a different exercise"
        )
    return _request_json(f"{CONTROL_URL}{endpoint}", {})


def _validate_option(
    inject: InjectOption,
    payload_key: str,
    value: Any,
    label: str,
) -> None:
    options = inject.payload.get(payload_key)
    if options and value not in options:
        raise ValueError(f"Unsupported {label}: {value}")


def _control_metadata(exercise: Exercise) -> dict[str, Any] | None:
    metadata_path = Path(exercise.package_path) / "chaos" / "control.json"
    try:
        return json.loads(metadata_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _effective_state_view(state: dict[str, Any]) -> dict[str, Any]:
    active_actions = state.get("active_actions", {})
    if not any("effect" in active for active in active_actions.values()):
        return state

    current = datetime.now(timezone.utc)
    live_actions = {}
    conditions = {
        "latency_ms": 0,
        "error_rate": 0.0,
        "auth_failure_rate": 0.0,
        "dns_failure_rate": 0.0,
        "data_integrity": False,
        "backup_delay": False,
        "build_blocked": False,
        "file_impact": False,
    }
    for action, active in active_actions.items():
        expires_at = active.get("expires_at")
        if expires_at and _parse_timestamp(expires_at) <= current:
            continue
        live_actions[action] = active
        for field, value in active.get("effect", {}).items():
            if isinstance(value, bool):
                conditions[field] = conditions[field] or value
            else:
                conditions[field] = max(conditions[field], value)
    return {
        **state,
        "active_actions": live_actions,
        "conditions": conditions,
    }


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _request_json(
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 4,
) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        detail = _http_error_detail(exc)
        if exc.code in {409, 503}:
            raise ChaosPreflightError(detail) from exc
        raise ChaosExecutionError(detail) from exc
    except (OSError, URLError, json.JSONDecodeError) as exc:
        raise ChaosExecutionError(f"Chaos controller request failed: {exc}") from exc


def _http_error_detail(error: HTTPError) -> str:
    try:
        payload = json.loads(error.read())
        return str(payload.get("detail") or payload)
    except (json.JSONDecodeError, OSError):
        return f"Chaos controller returned HTTP {error.code}"


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
