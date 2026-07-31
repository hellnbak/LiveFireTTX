from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import sqlite3

from app import models


class ModelMigrationTests(TestCase):
    def test_existing_database_adds_and_updates_trigger_count(self) -> None:
        with TemporaryDirectory() as temporary:
            database = Path(temporary) / "livefirettx.db"
            with sqlite3.connect(database) as connection:
                connection.execute(
                    """
                    CREATE TABLE inject_options (
                        id TEXT PRIMARY KEY,
                        exercise_id TEXT NOT NULL,
                        stage TEXT NOT NULL,
                        title TEXT NOT NULL,
                        audience TEXT NOT NULL,
                        description TEXT NOT NULL,
                        action_type TEXT NOT NULL,
                        script_name TEXT,
                        payload TEXT NOT NULL,
                        triggered INTEGER NOT NULL DEFAULT 0,
                        triggered_at TEXT
                    )
                    """
                )

            with patch.object(models, "DB_PATH", database):
                models.init_db()
                exercise = models.Exercise(
                    id="ttx_test",
                    name="Test",
                    scenario_type="cloud_outage",
                    platform="local_docker",
                    business_system="Orders",
                    difficulty="intermediate",
                    duration_minutes=90,
                    participants=["Incident Commander"],
                    objectives=["Assess impact"],
                    status="created",
                    created_at="2026-01-01T00:00:00+00:00",
                    package_path=str(Path(temporary) / "ttx_test"),
                )
                inject = models.InjectOption(
                    id="inj_test",
                    exercise_id=exercise.id,
                    stage="02-chaos-options",
                    title="Degrade Application",
                    audience="Cloud Operations",
                    description="Safe test",
                    action_type="chaos_script",
                    script_name="chaos_cli.py",
                    payload={"action": "app_degradation"},
                )
                models.save_exercise(exercise)
                models.save_injects([inject])
                models.mark_inject_triggered(inject.id)
                models.mark_inject_triggered(inject.id)

                stored = models.get_inject(inject.id)
                self.assertIsNotNone(stored)
                self.assertTrue(stored.triggered)
                self.assertEqual(2, stored.trigger_count)

                models.save_objective_assessment(
                    exercise.id,
                    0,
                    "effective",
                    "Impact was scoped within ten minutes.",
                )
                models.save_objective_assessment(
                    exercise.id,
                    0,
                    "exemplary",
                    "Impact was scoped and communicated within ten minutes.",
                )
                assessments = models.list_objective_assessments(exercise.id)
                self.assertEqual(1, len(assessments))
                self.assertEqual("exemplary", assessments[0]["rating"])
                self.assertIn("communicated", assessments[0]["notes"])

                checkpoint = models.create_checkpoint(
                    exercise.id,
                    title="Decision review",
                    description="Review current impact.",
                    audience="Incident Commander",
                    expected_action="State the next decision.",
                    scheduled_offset_seconds=600,
                    objective_index=0,
                )
                self.assertEqual(
                    [checkpoint],
                    models.list_checkpoints(exercise.id),
                )
                self.assertTrue(models.complete_checkpoint(checkpoint.id))
                self.assertFalse(models.complete_checkpoint(checkpoint.id))

                action = models.create_improvement_action(
                    exercise.id,
                    title="Update escalation procedure",
                    owner="Incident Management",
                    due_date="2026-02-01",
                    notes="Add an explicit decision owner.",
                )
                self.assertEqual("open", action.status)
                self.assertTrue(
                    models.update_improvement_action_status(
                        action.id,
                        "completed",
                    )
                )
                stored_action = models.get_improvement_action(action.id)
                self.assertIsNotNone(stored_action)
                self.assertEqual("completed", stored_action.status)
                self.assertIsNotNone(stored_action.completed_at)
                self.assertEqual(models.SCHEMA_VERSION, models.database_schema_version())
                self.assertTrue(models.database_health()["healthy"])
