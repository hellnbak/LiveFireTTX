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
import logging
import re
import subprocess

import yaml

from app.config import settings
from app.models import Exercise, InjectOption
from app.services.paths import exercise_package_path


CONTROL_URL = settings.control_url
REQUEST_TIMEOUT_SECONDS = settings.request_timeout_seconds
PLAYBOOK_ID_PATTERN = r"[a-z0-9][a-z0-9_-]{0,63}"
PLAYBOOK_VERSION_PATTERN = r"\d{8}T\d{12}Z"
LOGGER = logging.getLogger("livefirettx.runtime")


class ChaosExecutionError(RuntimeError):
    pass


class ChaosPreflightError(ChaosExecutionError):
    pass


def read_chaos_state(exercise: Exercise) -> dict[str, Any] | None:
    state_path = exercise_package_path(
        exercise,
        "chaos",
        "state",
        "state.json",
    )
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
        status = _request_json(
            f"{CONTROL_URL}/health",
            timeout=min(REQUEST_TIMEOUT_SECONDS, 1),
        )
    except ChaosExecutionError:
        LOGGER.warning("Chaos controller health request failed")
        return {
            "mode": "guarded",
            "reachable": False,
            "ready": False,
            "exercise_id": exercise.id,
            "error": "Chaos controller is unavailable",
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


def read_dependency_status(exercise: Exercise) -> dict[str, Any]:
    if not _control_metadata(exercise):
        return {"reachable": False, "dependencies": []}
    try:
        result = _request_json(
            f"{CONTROL_URL}/dependencies",
            timeout=min(REQUEST_TIMEOUT_SECONDS, 1),
        )
    except ChaosExecutionError:
        LOGGER.warning("Chaos controller dependency request failed")
        return {
            "reachable": False,
            "dependencies": [],
            "error": "Dependency status is unavailable",
        }
    return {
        **result,
        "reachable": True,
        "matches_exercise": result.get("exercise_id") == exercise.id,
    }


def run_chaos_inject(
    exercise: Exercise,
    inject: InjectOption,
    intensity: str = "medium",
    duration_seconds: int = 300,
    guardrail_profile: str = "standard",
    pattern: str = "steady",
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
        _validate_option(inject, "patterns", pattern, "pattern")
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
                    "pattern": pattern,
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
            [
                "run",
                str(action),
                "--intensity",
                intensity,
                "--pattern",
                pattern,
                "--duration",
                str(duration_seconds),
            ],
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

    chaos_root = exercise_package_path(exercise, "chaos")
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


def read_playbook_configuration(exercise: Exercise) -> str:
    playbook_root = exercise_package_path(exercise, "chaos", "playbooks")
    try:
        playbook_path = next(iter(sorted(playbook_root.glob("*.yml"))))
        return playbook_path.read_text()
    except (FileNotFoundError, OSError, StopIteration):
        state = read_chaos_state(exercise) or {}
        playbooks = state.get("playbooks", {})
        if not playbooks:
            return ""
        return yaml.safe_dump(next(iter(playbooks.values())), sort_keys=False)


def read_playbook_definition(
    exercise: Exercise,
    playbook_id: str | None = None,
) -> dict[str, Any]:
    if playbook_id and not re.fullmatch(PLAYBOOK_ID_PATTERN, playbook_id):
        raise ValueError("Invalid playbook id")
    playbook_root = exercise_package_path(exercise, "chaos", "playbooks")
    candidates = (
        [playbook_root / f"{playbook_id}.yml"]
        if playbook_id
        else sorted(playbook_root.glob("*.yml"))
    )
    for path in candidates:
        try:
            playbook = yaml.safe_load(path.read_text())
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(playbook, dict):
            return playbook

    state = read_chaos_state(exercise) or {}
    playbooks = state.get("playbooks", {})
    if playbook_id:
        return dict(playbooks.get(playbook_id, {}))
    if playbooks:
        return dict(next(iter(playbooks.values())))
    return {}


def read_playbook_library(exercise: Exercise) -> list[dict[str, Any]]:
    state = read_chaos_state(exercise) or {}
    library = []
    for playbook_id, state_playbook in state.get("playbooks", {}).items():
        playbook = read_playbook_definition(exercise, playbook_id)
        definition = playbook or dict(state_playbook)
        library.append(
            {
                **definition,
                "versions": list_playbook_versions(exercise, playbook_id),
            }
        )
    return sorted(library, key=lambda playbook: playbook.get("name", ""))


def list_playbook_versions(
    exercise: Exercise,
    playbook_id: str,
) -> list[dict[str, str]]:
    if not re.fullmatch(PLAYBOOK_ID_PATTERN, playbook_id):
        raise ValueError("Invalid playbook id")
    history_root = exercise_package_path(
        exercise,
        "chaos",
        "playbooks",
        "history",
        playbook_id,
    )
    versions = []
    for path in sorted(history_root.glob("*.yml"), reverse=True):
        if not re.fullmatch(PLAYBOOK_VERSION_PATTERN, path.stem):
            continue
        try:
            created_at = datetime.strptime(
                path.stem,
                "%Y%m%dT%H%M%S%fZ",
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        versions.append(
            {
                "id": path.stem,
                "created_at": created_at.isoformat(),
            }
        )
    return versions


def validate_playbook_configuration(
    exercise: Exercise,
    configuration: str | dict[str, Any],
) -> dict[str, Any]:
    playbook = _parse_playbook_configuration(configuration)
    return _guarded_request(
        exercise,
        "/playbooks/validate",
        playbook,
    )


def save_playbook_configuration(
    exercise: Exercise,
    configuration: str | dict[str, Any],
) -> dict[str, Any]:
    playbook = _parse_playbook_configuration(configuration)
    playbook_id = str(playbook.get("id", ""))
    if not re.fullmatch(PLAYBOOK_ID_PATTERN, playbook_id):
        raise ValueError("Playbook id must use lowercase letters, numbers, _ or -")
    normalized = _guarded_request(
        exercise,
        f"/playbooks/{quote(playbook_id)}",
        playbook,
        method="PUT",
    )
    normalized_id = str(normalized.get("id", ""))
    if normalized_id != playbook_id or not re.fullmatch(
        PLAYBOOK_ID_PATTERN,
        normalized_id,
    ):
        raise ChaosExecutionError("Chaos controller returned an invalid playbook id")
    playbook_root = exercise_package_path(exercise, "chaos", "playbooks")
    playbook_root.mkdir(parents=True, exist_ok=True)
    playbook_path = exercise_package_path(
        exercise,
        "chaos",
        "playbooks",
        f"{normalized_id}.yml",
    )
    serialized = yaml.safe_dump(normalized, sort_keys=False)
    if playbook_path.exists():
        current = playbook_path.read_text()
        if current != serialized:
            history_root = exercise_package_path(
                exercise,
                "chaos",
                "playbooks",
                "history",
                normalized_id,
            )
            history_root.mkdir(parents=True, exist_ok=True)
            version_id = datetime.now(timezone.utc).strftime(
                "%Y%m%dT%H%M%S%fZ"
            )
            version_path = exercise_package_path(
                exercise,
                "chaos",
                "playbooks",
                "history",
                normalized_id,
                f"{version_id}.yml",
            )
            version_path.write_text(current)
    playbook_path.write_text(serialized)
    return normalized


def clone_playbook_configuration(
    exercise: Exercise,
    source_playbook_id: str,
    new_playbook_id: str,
    new_name: str,
) -> dict[str, Any]:
    if not re.fullmatch(PLAYBOOK_ID_PATTERN, new_playbook_id):
        raise ValueError("Invalid cloned playbook id")
    name = new_name.strip()
    if not name or len(name) > 120:
        raise ValueError("Cloned playbook name must be between 1 and 120 characters")
    if read_playbook_definition(exercise, new_playbook_id):
        raise ValueError(f"Playbook already exists: {new_playbook_id}")
    source = read_playbook_definition(exercise, source_playbook_id)
    if not source:
        raise ValueError(f"Playbook not found: {source_playbook_id}")
    clone = json.loads(json.dumps(source))
    clone["id"] = new_playbook_id
    clone["name"] = name
    clone["description"] = (
        f"Cloned from {source_playbook_id}. "
        f"{clone.get('description', '')}"
    )[:500]
    return save_playbook_configuration(exercise, clone)


def restore_playbook_version(
    exercise: Exercise,
    playbook_id: str,
    version_id: str,
) -> dict[str, Any]:
    if not re.fullmatch(PLAYBOOK_ID_PATTERN, playbook_id):
        raise ValueError("Invalid playbook id")
    if not re.fullmatch(PLAYBOOK_VERSION_PATTERN, version_id):
        raise ValueError("Invalid playbook version")
    version_path = exercise_package_path(
        exercise,
        "chaos",
        "playbooks",
        "history",
        playbook_id,
        f"{version_id}.yml",
    )
    try:
        configuration = version_path.read_text()
    except OSError as exc:
        raise ValueError("Playbook version not found") from exc
    return save_playbook_configuration(exercise, configuration)


def export_playbook_configuration(
    exercise: Exercise,
    playbook_id: str,
) -> str:
    playbook = read_playbook_definition(exercise, playbook_id)
    if not playbook:
        raise ValueError(f"Playbook not found: {playbook_id}")
    return yaml.safe_dump(playbook, sort_keys=False)


def start_chaos_playbook(
    exercise: Exercise,
    playbook_id: str,
) -> dict[str, Any]:
    return _guarded_request(
        exercise,
        f"/playbooks/{quote(playbook_id)}/start",
    )


def _parse_playbook_configuration(
    configuration: str | dict[str, Any],
) -> dict[str, Any]:
    if isinstance(configuration, dict):
        encoded = json.dumps(configuration).encode()
        playbook = configuration
    else:
        encoded = configuration.encode()
        try:
            playbook = yaml.safe_load(configuration)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid playbook YAML: {exc}") from exc
    if len(encoded) > 64 * 1024:
        raise ValueError("Playbook configuration is too large")
    if not isinstance(playbook, dict):
        raise ValueError("Playbook configuration must contain one object")
    return playbook


def control_chaos_playbook_run(
    exercise: Exercise,
    playbook_run_id: str,
    command: str,
) -> dict[str, Any]:
    if command not in {"pause", "resume", "stop", "replay"}:
        raise ValueError(f"Unsupported playbook command: {command}")
    return _guarded_request(
        exercise,
        f"/playbook-runs/{quote(playbook_run_id)}/{command}",
    )


def skip_chaos_playbook_stage(
    exercise: Exercise,
    playbook_run_id: str,
    stage_id: str,
) -> dict[str, Any]:
    return _guarded_request(
        exercise,
        (
            f"/playbook-runs/{quote(playbook_run_id)}"
            f"/stages/{quote(stage_id)}/skip"
        ),
    )


def _guarded_request(
    exercise: Exercise,
    endpoint: str,
    payload: dict[str, Any] | None = None,
    method: str = "POST",
) -> dict[str, Any]:
    status = read_control_status(exercise)
    if not status.get("reachable"):
        raise ChaosPreflightError("Guarded chaos controller is unavailable")
    if not status.get("matches_exercise"):
        raise ChaosPreflightError(
            "The running chaos controller belongs to a different exercise"
        )
    return _request_json(
        f"{CONTROL_URL}{endpoint}",
        {} if payload is None and method == "POST" else payload,
        method=method,
    )


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
    metadata_path = exercise_package_path(
        exercise,
        "chaos",
        "control.json",
    )
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
    timeout: float = REQUEST_TIMEOUT_SECONDS,
    method: str | None = None,
) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
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
        LOGGER.warning(
            "Chaos controller request failed (%s)",
            type(exc).__name__,
        )
        raise ChaosExecutionError("Chaos controller request failed") from exc


def _http_error_detail(error: HTTPError) -> str:
    try:
        payload = json.loads(error.read())
        return str(payload.get("detail") or payload)
    except (json.JSONDecodeError, OSError):
        return f"Chaos controller returned HTTP {error.code}"


def _safe_script_path(exercise: Exercise, script_name: str) -> Path:
    chaos_root = exercise_package_path(exercise, "chaos")
    script = exercise_package_path(exercise, "chaos", script_name)
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
