from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from app import models
from app.services.facilitator import (
    ClockTransitionError,
    clear_schedule,
    clock_snapshot,
    dispatch_due_injects,
    inject_schedule_snapshot,
    schedule_inject,
    transition_clock,
)


class FacilitatorOperationsTests(TestCase):
    def test_clock_tracks_pause_resume_and_completion(self) -> None:
        with TemporaryDirectory() as temporary:
            with patch.object(models, "DB_PATH", Path(temporary) / "clock.db"):
                models.init_db()
                exercise = self.exercise()
                models.save_exercise(exercise)

                started = transition_clock(
                    exercise.id,
                    "start",
                    self.time(12, 0),
                )
                self.assertEqual("running", started.status)
                self.assertEqual(
                    600,
                    clock_snapshot(started, self.time(12, 10))["elapsed_seconds"],
                )

                paused = transition_clock(
                    exercise.id,
                    "pause",
                    self.time(12, 10),
                )
                self.assertEqual("paused", paused.status)
                self.assertEqual(
                    600,
                    clock_snapshot(paused, self.time(12, 20))["elapsed_seconds"],
                )

                resumed = transition_clock(
                    exercise.id,
                    "resume",
                    self.time(12, 20),
                )
                self.assertEqual(600, resumed.paused_seconds)
                self.assertEqual(
                    900,
                    clock_snapshot(resumed, self.time(12, 25))["elapsed_seconds"],
                )

                completed = transition_clock(
                    exercise.id,
                    "complete",
                    self.time(12, 30),
                )
                snapshot = clock_snapshot(completed, self.time(13, 0))
                self.assertEqual("completed", snapshot["status"])
                self.assertEqual(1200, snapshot["elapsed_seconds"])

                reset = transition_clock(
                    exercise.id,
                    "reset",
                    self.time(13, 1),
                )
                self.assertEqual("created", reset.status)
                self.assertIsNone(reset.started_at)
                self.assertEqual(0, reset.paused_seconds)

    def test_clock_rejects_invalid_transition(self) -> None:
        with TemporaryDirectory() as temporary:
            with patch.object(models, "DB_PATH", Path(temporary) / "clock.db"):
                models.init_db()
                models.save_exercise(self.exercise())
                with self.assertRaisesRegex(
                    ClockTransitionError,
                    "Cannot pause",
                ):
                    transition_clock("ttx_test", "pause", self.time(12, 0))

    def test_scheduled_narrative_dispatches_once_when_due(self) -> None:
        with TemporaryDirectory() as temporary:
            with patch.object(models, "DB_PATH", Path(temporary) / "schedule.db"):
                models.init_db()
                exercise = self.exercise()
                inject = self.inject()
                models.save_exercise(exercise)
                models.save_injects([inject])
                schedule_inject(inject, exercise, 5, True)
                transition_clock(exercise.id, "start", self.time(12, 0))

                self.assertEqual(
                    [],
                    dispatch_due_injects(exercise.id, self.time(12, 4)),
                )
                self.assertEqual(
                    [inject.id],
                    dispatch_due_injects(exercise.id, self.time(12, 5)),
                )
                self.assertEqual(
                    [],
                    dispatch_due_injects(exercise.id, self.time(12, 6)),
                )

                delivered = models.get_inject(inject.id)
                self.assertIsNotNone(delivered)
                self.assertTrue(delivered.triggered)
                self.assertEqual(1, delivered.trigger_count)
                events = models.list_events(exercise.id)
                self.assertEqual("scheduled_inject_delivered", events[0]["event_type"])

    def test_paused_clock_holds_scheduled_delivery(self) -> None:
        with TemporaryDirectory() as temporary:
            with patch.object(models, "DB_PATH", Path(temporary) / "schedule.db"):
                models.init_db()
                exercise = self.exercise()
                inject = self.inject()
                models.save_exercise(exercise)
                models.save_injects([inject])
                schedule_inject(inject, exercise, 5, True)
                transition_clock(exercise.id, "start", self.time(12, 0))
                paused = transition_clock(exercise.id, "pause", self.time(12, 4))

                self.assertEqual(
                    [],
                    dispatch_due_injects(exercise.id, self.time(12, 30)),
                )
                schedule = inject_schedule_snapshot(
                    paused,
                    [models.get_inject(inject.id)],
                    self.time(12, 30),
                )[0]
                self.assertEqual("scheduled", schedule["status"])
                self.assertEqual(60, schedule["remaining_seconds"])

    def test_manual_schedule_becomes_due_and_can_be_cleared(self) -> None:
        with TemporaryDirectory() as temporary:
            with patch.object(models, "DB_PATH", Path(temporary) / "schedule.db"):
                models.init_db()
                exercise = self.exercise()
                inject = self.inject()
                models.save_exercise(exercise)
                models.save_injects([inject])
                scheduled = schedule_inject(inject, exercise, 5, False)
                running = transition_clock(exercise.id, "start", self.time(12, 0))

                self.assertEqual(
                    [],
                    dispatch_due_injects(exercise.id, self.time(12, 10)),
                )
                schedule = inject_schedule_snapshot(
                    running,
                    [scheduled],
                    self.time(12, 10),
                )[0]
                self.assertEqual("due", schedule["status"])
                self.assertFalse(schedule["auto_deliver"])

                cleared = clear_schedule(scheduled)
                self.assertIsNone(cleared.scheduled_offset_seconds)
                self.assertFalse(cleared.auto_deliver)

    def test_only_narrative_injects_can_be_scheduled(self) -> None:
        exercise = self.exercise()
        inject = self.inject(action_type="chaos_script")
        with self.assertRaisesRegex(ValueError, "Only narrative"):
            schedule_inject(inject, exercise, 5, True)

    @staticmethod
    def exercise() -> models.Exercise:
        return models.Exercise(
            id="ttx_test",
            name="Facilitator operations",
            scenario_type="cloud_outage",
            platform="local_docker",
            business_system="Orders",
            difficulty="intermediate",
            duration_minutes=60,
            participants=["Incident Commander"],
            objectives=["Assess impact"],
            status="created",
            created_at="2026-01-01T00:00:00+00:00",
            package_path="/tmp/ttx_test",
        )

    @staticmethod
    def inject(action_type: str = "narrative") -> models.InjectOption:
        return models.InjectOption(
            id="inj_test",
            exercise_id="ttx_test",
            stage="01-opening",
            title="Initial Situation Brief",
            audience="All Participants",
            description="The exercise begins.",
            action_type=action_type,
            script_name=None,
            payload={},
        )

    @staticmethod
    def time(hour: int, minute: int) -> datetime:
        return datetime(2026, 1, 1, hour, minute, tzinfo=timezone.utc)
