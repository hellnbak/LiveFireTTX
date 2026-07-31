from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from app import models
from app.models import Exercise
from app.services.paths import (
    PackagePathError,
    exercise_package_path,
    exercise_package_root,
    new_exercise_package_path,
    validate_exercise_id,
)


class PackagePathTests(TestCase):
    def test_derives_package_from_trusted_root_not_stored_path(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated_root = root / "generated"
            package_root = generated_root / "ttx_safe"
            package_root.mkdir(parents=True)
            exercise = self.exercise(root / "outside" / "ttx_safe")

            with patch.object(models, "GENERATED_ROOT", generated_root):
                self.assertEqual(
                    package_root.resolve(),
                    exercise_package_root(exercise),
                )
                self.assertEqual(
                    (package_root / "reports" / "report.md").resolve(),
                    exercise_package_path(
                        exercise,
                        "reports",
                        "report.md",
                    ),
                )

    def test_rejects_identifiers_traversal_and_filesystem_root(self) -> None:
        for exercise_id in ["../outside", "ttx_../../outside", "ttx_safe/escape"]:
            with self.subTest(exercise_id=exercise_id):
                with self.assertRaisesRegex(PackagePathError, "identifier"):
                    validate_exercise_id(exercise_id)
        with self.assertRaisesRegex(PackagePathError, "filesystem root"):
            new_exercise_package_path("ttx_safe", Path("/"))

    def test_rejects_traversal_and_symlink_escape(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated_root = root / "generated"
            package_root = generated_root / "ttx_safe"
            package_root.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            (package_root / "link").symlink_to(outside, target_is_directory=True)
            exercise = self.exercise(package_root)

            with patch.object(models, "GENERATED_ROOT", generated_root):
                with self.assertRaisesRegex(PackagePathError, "outside"):
                    exercise_package_path(exercise, "..", "outside.txt")
                with self.assertRaisesRegex(PackagePathError, "outside"):
                    exercise_package_path(exercise, "link", "secret.txt")

    @staticmethod
    def exercise(package_path: Path) -> Exercise:
        return Exercise(
            id="ttx_safe",
            name="Safe paths",
            scenario_type="dependency_cascade",
            platform="local_docker",
            business_system="Commerce",
            difficulty="advanced",
            duration_minutes=90,
            participants=[],
            objectives=[],
            status="created",
            created_at="2026-01-01T00:00:00+00:00",
            package_path=str(package_path),
        )
