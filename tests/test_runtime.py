from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from app.models import Exercise, InjectOption
from app.services.runtime import run_chaos_inject


class RuntimeSafetyTests(TestCase):
    def test_chaos_script_cannot_escape_generated_directory(self) -> None:
        with TemporaryDirectory() as temporary:
            exercise = Exercise(
                id="ttx_test",
                name="Test",
                scenario_type="cloud_outage",
                platform="local_docker",
                business_system="Orders",
                difficulty="intermediate",
                duration_minutes=90,
                participants=[],
                objectives=[],
                status="created",
                created_at="2026-01-01T00:00:00+00:00",
                package_path=str(Path(temporary)),
            )
            inject = InjectOption(
                id="inj_test",
                exercise_id=exercise.id,
                stage="02-chaos-options",
                title="Invalid",
                audience="Test",
                description="Test",
                action_type="chaos_script",
                script_name="../outside.py",
                payload={},
            )

            with self.assertRaisesRegex(ValueError, "Invalid chaos script path"):
                run_chaos_inject(exercise, inject)
