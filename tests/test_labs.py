from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from app import models
from app.models import Exercise
from app.services import labs


class LabLifecycleTests(TestCase):
    def test_runs_only_fixed_compose_operation_from_contained_package(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated_root = root / "generated"
            target = generated_root / "ttx_lab" / "target"
            target.mkdir(parents=True)
            compose = target / "docker-compose.yml"
            compose.write_text("services: {}\n")
            docker = root / "docker"
            docker.write_text("binary")
            docker.chmod(0o755)
            exercise = self.exercise()
            settings = SimpleNamespace(
                lab_controls_enabled=True,
                lab_command_timeout_seconds=30,
            )
            completed = SimpleNamespace(returncode=0, stdout="ready", stderr="")
            with (
                patch.object(models, "GENERATED_ROOT", generated_root),
                patch.object(labs, "settings", settings),
                patch("app.services.labs.shutil.which", return_value=str(docker)),
                patch("app.services.labs.subprocess.run", return_value=completed) as run,
            ):
                result = labs.run_lab_operation(exercise, "deploy")

            self.assertTrue(result["success"])
            command = run.call_args.args[0]
            self.assertEqual(str(docker.resolve()), command[0])
            self.assertEqual(
                [
                    "compose",
                    "-f",
                    str(compose.resolve()),
                    "up",
                    "-d",
                    "--build",
                    "--wait",
                ],
                command[1:],
            )
            self.assertNotIn("shell", run.call_args.kwargs)
            self.assertEqual(str(target.resolve()), run.call_args.kwargs["cwd"])

    def test_rejects_symlinked_compose_definition(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            generated_root = root / "generated"
            target = generated_root / "ttx_lab" / "target"
            target.mkdir(parents=True)
            external = root / "external.yml"
            external.write_text("services: {}\n")
            (target / "docker-compose.yml").symlink_to(external)
            docker = root / "docker"
            docker.write_text("binary")
            docker.chmod(0o755)
            settings = SimpleNamespace(
                lab_controls_enabled=True,
                lab_command_timeout_seconds=30,
            )
            with (
                patch.object(models, "GENERATED_ROOT", generated_root),
                patch.object(labs, "settings", settings),
                patch("app.services.labs.shutil.which", return_value=str(docker)),
            ):
                with self.assertRaisesRegex(labs.LabOperationError, "symlink"):
                    labs.run_lab_operation(self.exercise(), "deploy")

    @staticmethod
    def exercise() -> Exercise:
        return Exercise(
            id="ttx_lab",
            name="Lab Test",
            scenario_type="cloud_outage",
            platform="local_docker",
            business_system="Orders",
            difficulty="intermediate",
            duration_minutes=60,
            participants=["Incident Commander"],
            objectives=["Assess impact"],
            status="created",
            created_at="2026-01-01T00:00:00+00:00",
            package_path="/tmp/untrusted",
        )
