from __future__ import annotations

from pathlib import Path
import os
import re

from app import models
from app.models import Exercise


EXERCISE_ID_PATTERN = r"ttx_[a-z0-9][a-z0-9_-]{0,59}"


class PackagePathError(ValueError):
    pass


def validate_exercise_id(exercise_id: str) -> str:
    if not re.fullmatch(EXERCISE_ID_PATTERN, exercise_id):
        raise PackagePathError("Invalid exercise identifier")
    return exercise_id


def new_exercise_package_path(
    exercise_id: str,
    generated_root: Path | None = None,
) -> Path:
    trusted_root = _trusted_generated_root(generated_root)
    return _contained_path(trusted_root, validate_exercise_id(exercise_id))


def exercise_package_root(
    exercise: Exercise,
    *,
    generated_root: Path | None = None,
    require_directory: bool = False,
) -> Path:
    exercise_id = validate_exercise_id(exercise.id)
    package_root = new_exercise_package_path(exercise_id, generated_root)
    if require_directory and not package_root.is_dir():
        raise PackagePathError("Exercise package is unavailable")
    return package_root


def exercise_package_path(
    exercise: Exercise,
    *parts: str,
    generated_root: Path | None = None,
) -> Path:
    package_root = exercise_package_root(
        exercise,
        generated_root=generated_root,
    )
    return _contained_path(package_root, *parts)


def _trusted_generated_root(generated_root: Path | None) -> Path:
    configured = generated_root if generated_root is not None else models.GENERATED_ROOT
    resolved = Path(os.path.realpath(configured))
    if resolved == Path(resolved.anchor):
        raise PackagePathError("Generated package root cannot be a filesystem root")
    return resolved


def _contained_path(root: Path, *parts: str) -> Path:
    trusted_root = os.path.realpath(root)
    candidate = os.path.realpath(os.path.join(trusted_root, *parts))
    prefix = trusted_root.rstrip(os.sep) + os.sep
    if not candidate.startswith(prefix):
        raise PackagePathError("Path resolves outside the exercise package")
    return Path(candidate)
