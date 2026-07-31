from __future__ import annotations

from pathlib import Path
from typing import Any
import re

import yaml

from app.models import Exercise, SCENARIO_LIBRARY


ROLE_BRIEF_PATTERN = r"\d{2}-[a-z0-9][a-z0-9-]{0,63}\.md"


def list_participant_briefs(exercise: Exercise) -> list[dict[str, str]]:
    index_path = Path(exercise.package_path) / "participants" / "index.yml"
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
    package_root = Path(exercise.package_path).resolve()
    roles_root = (package_root / "participants" / "roles").resolve()
    brief = (roles_root / filename).resolve()
    if (
        package_root not in roles_root.parents
        or roles_root not in brief.parents
        or not brief.is_file()
    ):
        raise ValueError("Participant brief is unavailable")
    return brief


def dependency_map(exercise: Exercise) -> list[dict[str, Any]]:
    scenario = SCENARIO_LIBRARY.get(exercise.scenario_type, {})
    dependencies = scenario.get("dependencies", [])
    return [dict(item) for item in dependencies if isinstance(item, dict)]
