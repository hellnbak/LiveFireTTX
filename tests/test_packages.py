from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from zipfile import ZipFile
from io import BytesIO

from app import models
from app.models import Exercise
from app.services.packages import (
    build_exercise_archive,
    dependency_map,
    list_participant_briefs,
    participant_brief_path,
)


class PackageMaterialTests(TestCase):
    def test_lists_and_contains_participant_briefs(self) -> None:
        with TemporaryDirectory() as temporary:
            generated_root = Path(temporary)
            package = generated_root / "ttx_package"
            roles = package / "participants" / "roles"
            roles.mkdir(parents=True)
            brief = roles / "01-incident-commander.md"
            brief.write_text("# Simulated role\n")
            (package / "participants" / "index.yml").write_text(
                """
roles:
  - role: Incident Commander
    file: roles/01-incident-commander.md
"""
            )
            exercise = self.exercise(package)
            with patch.object(models, "GENERATED_ROOT", generated_root):
                self.assertEqual(
                    [
                        {
                            "role": "Incident Commander",
                            "filename": "01-incident-commander.md",
                        }
                    ],
                    list_participant_briefs(exercise),
                )
                self.assertEqual(
                    brief.resolve(),
                    participant_brief_path(exercise, brief.name),
                )
                with ZipFile(BytesIO(build_exercise_archive(exercise))) as archive:
                    self.assertIn(
                        "participants/roles/01-incident-commander.md",
                        archive.namelist(),
                    )
                self.assertTrue(dependency_map(exercise))

    def test_rejects_participant_path_escape(self) -> None:
        with TemporaryDirectory() as temporary:
            generated_root = Path(temporary)
            package = generated_root / "ttx_package"
            package.mkdir()
            exercise = self.exercise(package)
            with patch.object(models, "GENERATED_ROOT", generated_root):
                with self.assertRaisesRegex(ValueError, "Invalid"):
                    participant_brief_path(exercise, "../outside.md")

    def test_ignores_forged_package_path_and_rejects_symlinks(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated_root = root / "generated"
            package = generated_root / "ttx_package"
            package.mkdir(parents=True)
            outside = root / "outside"
            outside.mkdir()
            (outside / "secret.md").write_text("secret")
            exercise = self.exercise(outside / "ttx_package")

            with patch.object(models, "GENERATED_ROOT", generated_root):
                with self.assertRaisesRegex(ValueError, "unavailable"):
                    participant_brief_path(exercise, "01-secret.md")
                (package / "escape").symlink_to(outside, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, "symbolic links"):
                    build_exercise_archive(exercise)

    @staticmethod
    def exercise(package: Path) -> Exercise:
        return Exercise(
            id="ttx_package",
            name="Package",
            scenario_type="dependency_cascade",
            platform="local_docker",
            business_system="Commerce",
            difficulty="advanced",
            duration_minutes=90,
            participants=["Incident Commander"],
            objectives=["Coordinate"],
            status="created",
            created_at="2026-01-01T00:00:00+00:00",
            package_path=str(package),
        )
