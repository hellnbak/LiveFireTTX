from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any
import re
from zipfile import ZIP_DEFLATED, ZipFile

import yaml

from app.models import Exercise, SCENARIO_LIBRARY
from app.services.paths import (
    PackagePathError,
    exercise_package_path,
    exercise_package_root,
)


ROLE_BRIEF_PATTERN = r"\d{2}-[a-z0-9][a-z0-9-]{0,63}\.md"
MAX_EXERCISE_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_EXERCISE_ARCHIVE_FILES = 2000


def list_participant_briefs(exercise: Exercise) -> list[dict[str, str]]:
    index_path = exercise_package_path(
        exercise,
        "participants",
        "index.yml",
    )
    try:
        payload = yaml.safe_load(index_path.read_text())
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(payload, dict) or not isinstance(payload.get("roles"), list):
        return []
    briefs = []
    for item in payload["roles"]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        relative = str(item.get("file", ""))
        filename = Path(relative).name
        if role and re.fullmatch(ROLE_BRIEF_PATTERN, filename):
            briefs.append({"role": role, "filename": filename})
    return briefs


def participant_brief_path(exercise: Exercise, filename: str) -> Path:
    if not re.fullmatch(ROLE_BRIEF_PATTERN, filename):
        raise ValueError("Invalid participant brief")
    brief = exercise_package_path(
        exercise,
        "participants",
        "roles",
        filename,
    )
    if not brief.is_file():
        raise ValueError("Participant brief is unavailable")
    return brief


def participant_brief_content(exercise: Exercise, filename: str) -> bytes:
    brief = participant_brief_path(exercise, filename)
    if brief.stat().st_size > 1024 * 1024:
        raise ValueError("Participant brief is unavailable")
    return brief.read_bytes()


def build_exercise_archive(exercise: Exercise) -> bytes:
    package_root = exercise_package_root(exercise, require_directory=True)
    files: list[tuple[Path, str]] = []
    total_size = 0
    for candidate in sorted(package_root.rglob("*")):
        if candidate.is_symlink():
            raise PackagePathError("Exercise package cannot contain symbolic links")
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(package_root)
        safe_file = exercise_package_path(exercise, *relative.parts)
        total_size += safe_file.stat().st_size
        files.append((safe_file, relative.as_posix()))
        if (
            len(files) > MAX_EXERCISE_ARCHIVE_FILES
            or total_size > MAX_EXERCISE_ARCHIVE_BYTES
        ):
            raise PackagePathError("Exercise package is too large to download")

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for safe_file, archive_name in files:
            archive.writestr(archive_name, safe_file.read_bytes())
    return output.getvalue()


def dependency_map(exercise: Exercise) -> list[dict[str, Any]]:
    scenario = SCENARIO_LIBRARY.get(exercise.scenario_type, {})
    dependencies = scenario.get("dependencies", [])
    return [dict(item) for item in dependencies if isinstance(item, dict)]
