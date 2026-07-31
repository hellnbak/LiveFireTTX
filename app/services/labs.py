from __future__ import annotations

from pathlib import Path
from typing import Any
import logging
import os
import shutil
import subprocess

from app.config import settings
from app.models import Exercise
from app.services.paths import exercise_package_path, exercise_package_root


LAB_OPERATIONS = {"deploy", "validate", "destroy"}
MAX_LAB_OUTPUT_CHARACTERS = 8000
LOGGER = logging.getLogger("livefirettx.labs")


class LabOperationError(RuntimeError):
    pass


def lab_snapshot(exercise: Exercise) -> dict[str, Any]:
    docker = _docker_binary()
    try:
        compose_file = _compose_file(exercise)
        package_ready = compose_file.is_file()
    except (OSError, ValueError):
        package_ready = False
    return {
        "enabled": settings.lab_controls_enabled,
        "docker_available": docker is not None,
        "package_ready": package_ready,
        "can_control": bool(
            settings.lab_controls_enabled and docker and package_ready
        ),
        "mode": "host" if docker else "manual",
    }


def run_lab_operation(exercise: Exercise, operation: str) -> dict[str, Any]:
    if operation not in LAB_OPERATIONS:
        raise LabOperationError("Unsupported lab operation")
    if not settings.lab_controls_enabled:
        raise LabOperationError("One-click lab controls are disabled")
    docker = _docker_binary()
    if not docker:
        raise LabOperationError("Docker CLI is unavailable; use the package scripts")
    compose_file = _compose_file(exercise)
    command = _operation_command(docker, compose_file, operation)
    try:
        process = subprocess.run(
            command,
            cwd=str(compose_file.parent),
            env=_docker_environment(),
            capture_output=True,
            text=True,
            timeout=settings.lab_command_timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LabOperationError(
            f"Lab {operation} timed out after "
            f"{settings.lab_command_timeout_seconds} seconds"
        ) from exc
    except OSError as exc:
        raise LabOperationError("Docker could not start the lab operation") from exc

    output = "\n".join(
        part.strip() for part in (process.stdout, process.stderr) if part.strip()
    )[-MAX_LAB_OUTPUT_CHARACTERS:]
    if process.returncode != 0:
        LOGGER.warning("Lab %s failed: %s", operation, output or "no output")
        raise LabOperationError(
            f"Lab {operation} failed; review the local application log"
        )
    return {
        "operation": operation,
        "success": True,
        "output": output or f"Lab {operation} completed",
    }


def _compose_file(exercise: Exercise) -> Path:
    package_root = exercise_package_root(exercise, require_directory=True)
    candidate = package_root / "target" / "docker-compose.yml"
    if candidate.is_symlink():
        raise LabOperationError("Generated lab Compose file cannot be a symlink")
    compose_file = exercise_package_path(
        exercise,
        "target",
        "docker-compose.yml",
    )
    if not compose_file.is_file():
        raise LabOperationError("Generated lab Compose file is unavailable")
    return compose_file


def _docker_binary() -> Path | None:
    candidate = shutil.which("docker")
    if not candidate:
        return None
    binary = Path(candidate)
    if binary.name != "docker" or not binary.is_file():
        return None
    return binary.resolve()


def _operation_command(
    docker: Path,
    compose_file: Path,
    operation: str,
) -> list[str]:
    base = [str(docker), "compose", "-f", str(compose_file)]
    if operation == "deploy":
        return [*base, "up", "-d", "--build", "--wait"]
    if operation == "validate":
        return [*base, "ps"]
    return [*base, "down", "-v", "--remove-orphans"]


def _docker_environment() -> dict[str, str]:
    allowed_names = {
        "DOCKER_CONTEXT",
        "DOCKER_HOST",
        "HOME",
        "LIVEFIRE_CONTROL_HOST_PORT",
        "LIVEFIRE_TARGET_HOST_PORT",
        "PATH",
    }
    environment = {
        name: value for name, value in os.environ.items() if name in allowed_names
    }
    if hasattr(os, "getuid"):
        environment["LIVEFIRE_RUNTIME_UID"] = str(os.getuid())
    if hasattr(os, "getgid"):
        environment["LIVEFIRE_RUNTIME_GID"] = str(os.getgid())
    return environment
