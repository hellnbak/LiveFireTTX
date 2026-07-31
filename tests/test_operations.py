from __future__ import annotations

from datetime import datetime, timezone
from unittest import TestCase

from app.models import Exercise, ExerciseCheckpoint, InjectOption
from app.services.operations import build_run_of_show, participant_snapshot


class ExerciseOperationsTests(TestCase):
    def test_builds_unified_timeline_and_selects_due_action(self) -> None:
        exercise = self.exercise(status="running")
        exercise.started_at = "2026-01-01T12:00:00+00:00"
        opening = self.inject("inj_open", "Opening", "narrative", 0)
        opening.triggered = True
        opening.triggered_at = "2026-01-01T12:00:01+00:00"
        executive = self.inject("inj_exec", "Executive Request", "narrative", 600)
        chaos = self.inject("inj_chaos", "Degrade API", "chaos_script", None)
        checkpoint = ExerciseCheckpoint(
            id="chk_decision",
            exercise_id=exercise.id,
            title="Decision Review",
            description="Review current impact.",
            audience="Incident Commander",
            expected_action="State the next decision.",
            scheduled_offset_seconds=300,
            objective_index=0,
            status="pending",
            created_at="2026-01-01T00:00:00+00:00",
        )

        timeline = build_run_of_show(
            exercise,
            [opening, executive, chaos],
            [checkpoint],
            datetime(2026, 1, 1, 12, 6, tzinfo=timezone.utc),
        )

        self.assertEqual("Decision Review", timeline["next_entry"]["title"])
        self.assertEqual("due", timeline["next_entry"]["status"])
        self.assertEqual(1, timeline["due_count"])
        self.assertEqual("Degrade API", timeline["entries"][-1]["title"])

    def test_participant_snapshot_hides_future_and_chaos_injects(self) -> None:
        exercise = self.exercise(status="running")
        delivered = self.inject("inj_open", "Opening", "narrative", 0)
        delivered.triggered = True
        delivered.triggered_at = "2026-01-01T12:00:01+00:00"
        future = self.inject("inj_future", "Future", "narrative", 1200)
        chaos = self.inject("inj_chaos", "Degrade API", "chaos_script", None)
        chaos.triggered = True
        chaos.triggered_at = "2026-01-01T12:05:00+00:00"

        snapshot = participant_snapshot(exercise, [future, chaos, delivered])

        self.assertEqual("Opening", snapshot["current_inject"]["title"])
        self.assertEqual(1, len(snapshot["delivered_injects"]))
        self.assertNotIn("Future", str(snapshot))
        self.assertNotIn("Degrade API", str(snapshot))

    @staticmethod
    def exercise(status: str) -> Exercise:
        return Exercise(
            id="ttx_operations",
            name="Operations Test",
            scenario_type="cloud_outage",
            platform="local_docker",
            business_system="Orders",
            difficulty="intermediate",
            duration_minutes=60,
            participants=["Incident Commander"],
            objectives=["Assess impact"],
            status=status,
            created_at="2026-01-01T00:00:00+00:00",
            package_path="/tmp/ignored",
        )

    @staticmethod
    def inject(
        inject_id: str,
        title: str,
        action_type: str,
        offset: int | None,
    ) -> InjectOption:
        return InjectOption(
            id=inject_id,
            exercise_id="ttx_operations",
            stage="01-operations",
            title=title,
            audience="All Participants",
            description=f"{title} description",
            action_type=action_type,
            script_name="chaos_cli.py" if action_type == "chaos_script" else None,
            payload={},
            scheduled_offset_seconds=offset,
        )
