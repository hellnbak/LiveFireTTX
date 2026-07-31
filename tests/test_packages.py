from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from app.models import Exercise
from app.services.packages import (
    dependency_map,
    list_participant_briefs,
    participant_brief_path,
)


class PackageMaterialTests(TestCase):
    def test_lists_and_contains_participant_briefs(self) -> None:
        with TemporaryDirectory() as temporary:
            package = Path(temporary)
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
            self.assertTrue(dependency_map(exercise))

    def test_rejects_participant_path_escape(self) -> None:
        with TemporaryDirectory() as temporary:
            exercise = self.exercise(Path(temporary))
            with self.assertRaisesRegex(ValueError, "Invalid"):
                participant_brief_path(exercise, "../outside.md")

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
