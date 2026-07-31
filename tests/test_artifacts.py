from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from app import models
from app.models import Exercise
from app.services.artifacts import (
    artifact_trigger_result,
    create_safe_artifact_inject,
)


class SafeArtifactTests(TestCase):
    def test_creates_watermarked_package_scoped_artifact(self) -> None:
        with TemporaryDirectory() as temporary:
            generated_root = Path(temporary)
            exercise = self.exercise(generated_root / "ttx_artifact")
            with patch.object(models, "GENERATED_ROOT", generated_root):
                inject = create_safe_artifact_inject(
                    exercise,
                    "Vendor Escalation",
                    "Engineering",
                    "03-facilitator-artifacts",
                    "vendor_advisory",
                    "The simulated vendor reports an unresolved dependency issue.",
                )
                artifact_path = (
                    Path(exercise.package_path)
                    / str(inject.payload["artifact"])
                )

                self.assertTrue(artifact_path.is_file())
                self.assertTrue(inject.payload["safe"])
                self.assertTrue(inject.payload["facilitator_defined"])
                content = artifact_path.read_text()
                self.assertIn("SIMULATED EXERCISE ARTIFACT", content)
                self.assertIn("DO NOT TREAT AS A REAL INCIDENT RECORD", content)
                self.assertIn(
                    "Prepared safe exercise artifact",
                    artifact_trigger_result(exercise, inject),
                )

    def test_rejects_artifact_reference_outside_package(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            exercise = self.exercise(root / "ttx_artifact")
            with patch.object(models, "GENERATED_ROOT", root):
                inject = create_safe_artifact_inject(
                    exercise,
                    "Customer Escalation",
                    "Communications",
                    "03-facilitator-artifacts",
                    "customer_message",
                    "A simulated customer requests an incident update.",
                )
                outside = root / "outside.md"
                outside.write_text("outside")
                inject.payload["artifact"] = "../outside.md"

                with self.assertRaisesRegex(
                    ValueError,
                    "outside the exercise package",
                ):
                    artifact_trigger_result(exercise, inject)

    def test_rejects_multiline_title_and_unknown_type(self) -> None:
        with TemporaryDirectory() as temporary:
            generated_root = Path(temporary)
            exercise = self.exercise(generated_root / "ttx_artifact")
            with patch.object(models, "GENERATED_ROOT", generated_root):
                with self.assertRaisesRegex(ValueError, "single line"):
                    create_safe_artifact_inject(
                        exercise,
                        "Unsafe\nTitle",
                        "Operations",
                        "03-artifacts",
                        "security_alert",
                        "Synthetic content",
                    )

    def test_rejects_symlinked_artifact_directory(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            exercise = self.exercise(root / "ttx_artifact")
            outside = root / "outside"
            outside.mkdir()
            artifacts = Path(exercise.package_path) / "artifacts"
            artifacts.symlink_to(outside, target_is_directory=True)

            with patch.object(models, "GENERATED_ROOT", root):
                with self.assertRaisesRegex(ValueError, "outside the exercise package"):
                    create_safe_artifact_inject(
                        exercise,
                        "Title",
                        "Operations",
                        "03-artifacts",
                        "security_alert",
                        "Synthetic content",
                    )
                with self.assertRaisesRegex(ValueError, "Unknown safe artifact"):
                    create_safe_artifact_inject(
                        exercise,
                        "Title",
                        "Operations",
                        "03-artifacts",
                        "executable",
                        "Synthetic content",
                    )

    def exercise(self, package_path: Path) -> Exercise:
        package_path.mkdir(parents=True)
        return Exercise(
            id="ttx_artifact",
            name="Artifact Test",
            scenario_type="cloud_outage",
            platform="local_docker",
            business_system="Orders",
            difficulty="intermediate",
            duration_minutes=90,
            participants=[],
            objectives=[],
            status="created",
            created_at="2026-01-01T00:00:00Z",
            package_path=str(package_path),
        )
