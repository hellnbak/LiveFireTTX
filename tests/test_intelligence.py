from __future__ import annotations

from io import BytesIO
from unittest import TestCase
from zipfile import ZipFile

from app.models import Exercise, InjectOption
from app.services.intelligence import (
    build_evidence_archive,
    build_exercise_intelligence,
    render_evidence_markdown,
)


class ExerciseIntelligenceTests(TestCase):
    def test_builds_scores_and_run_comparison_from_evidence(self) -> None:
        exercise = self.exercise()
        events = self.events()
        state = self.chaos_state()
        intelligence = build_exercise_intelligence(
            exercise,
            self.injects(),
            events,
            state,
            [
                {
                    "objective_index": 0,
                    "rating": "effective",
                    "notes": "Impact scoped quickly.",
                    "updated_at": "2026-01-01T00:10:00Z",
                },
                {
                    "objective_index": 1,
                    "rating": "exemplary",
                    "notes": "Status updates were decision-oriented.",
                    "updated_at": "2026-01-01T00:20:00Z",
                },
            ],
        )

        self.assertEqual(83, intelligence["objective_score"])
        self.assertEqual(50, intelligence["inject_coverage"])
        self.assertEqual(100, intelligence["safe_run_rate"])
        self.assertEqual(83, intelligence["readiness_score"])
        self.assertTrue(intelligence["assessment_complete"])
        self.assertEqual(1, intelligence["guardrail_stops"])
        self.assertEqual(2, len(intelligence["run_comparison"]))
        degradation = next(
            run
            for run in intelligence["run_comparison"]
            if run["action"] == "app_degradation"
        )
        self.assertEqual(
            2500,
            degradation["peak_conditions"]["latency_ms"],
        )
        self.assertEqual(
            0.2,
            degradation["peak_conditions"]["error_rate"],
        )
        self.assertGreater(degradation["impact_score"], 0)

    def test_exports_markdown_and_safe_csv_evidence_archive(self) -> None:
        exercise = self.exercise()
        events = self.events()
        state = self.chaos_state()
        intelligence = build_exercise_intelligence(
            exercise,
            self.injects(),
            events,
            state,
            [],
            [
                {
                    "id": "imp_one",
                    "title": "Update escalation path",
                    "owner": "Incident Management",
                    "due_date": "2026-02-01",
                    "status": "open",
                    "notes": "Define the decision owner.",
                    "created_at": "2026-01-01T01:00:00Z",
                    "completed_at": None,
                }
            ],
            [
                {
                    "id": "chk_one",
                    "title": "Decision review",
                    "description": "Review impact.",
                    "audience": "Incident Commander",
                    "expected_action": "State the next decision.",
                    "scheduled_offset_seconds": 600,
                    "objective_index": 0,
                    "status": "completed",
                    "created_at": "2026-01-01T00:00:00Z",
                    "completed_at": "2026-01-01T00:10:00Z",
                }
            ],
        )
        markdown = render_evidence_markdown(
            exercise,
            intelligence,
            events,
            state,
        )
        self.assertIn("# After Action Evidence: Intelligence Test", markdown)
        self.assertIn("- Lifecycle status: created", markdown)
        self.assertIn("- Recorded exercise time: 0 seconds", markdown)
        self.assertIn("## Chaos Run Comparison", markdown)
        self.assertIn("## Improvement Plan", markdown)
        self.assertIn("Update escalation path", markdown)
        self.assertIn("Decision review", markdown)
        self.assertIn("app_degradation", markdown)

        payload = build_evidence_archive(
            exercise,
            intelligence,
            events,
            state,
        )
        with ZipFile(BytesIO(payload)) as archive:
            self.assertEqual(
                {
                    "after_action_report.md",
                    "manifest.json",
                    "events.csv",
                    "chaos_runs.csv",
                    "objective_assessments.csv",
                    "msel_checkpoints.csv",
                    "improvement_actions.csv",
                    "chaos_state.json",
                },
                set(archive.namelist()),
            )
            events_csv = archive.read("events.csv").decode()
            self.assertIn("'=unsafe spreadsheet formula", events_csv)
            self.assertIn(
                '"schema_version": 3',
                archive.read("manifest.json").decode(),
            )
            self.assertIn(
                '"exercise_clock"',
                archive.read("manifest.json").decode(),
            )

    def exercise(self) -> Exercise:
        return Exercise(
            id="ttx_intelligence",
            name="Intelligence Test",
            scenario_type="cloud_outage",
            platform="local_docker",
            business_system="Orders",
            difficulty="intermediate",
            duration_minutes=90,
            participants=["Incident Commander"],
            objectives=[
                "Assess business impact",
                "Communicate outage status",
            ],
            status="created",
            created_at="2026-01-01T00:00:00Z",
            package_path="/tmp/ttx_intelligence",
        )

    def injects(self) -> list[InjectOption]:
        return [
            InjectOption(
                id="inj_one",
                exercise_id="ttx_intelligence",
                stage="01-opening",
                title="Opening",
                audience="All",
                description="Start",
                action_type="narrative",
                script_name=None,
                payload={},
                triggered=True,
            ),
            InjectOption(
                id="inj_two",
                exercise_id="ttx_intelligence",
                stage="02-chaos",
                title="Degrade",
                audience="Operations",
                description="Degrade",
                action_type="chaos_script",
                script_name="chaos_cli.py",
                payload={"action": "app_degradation"},
            ),
        ]

    def events(self) -> list[dict[str, str]]:
        return [
            {
                "created_at": "2026-01-01T00:00:00Z",
                "event_type": "exercise_created",
                "title": "Created",
                "detail": "Created",
            },
            {
                "created_at": "2026-01-01T00:10:00Z",
                "event_type": "manual_note",
                "title": "Decision",
                "detail": "=unsafe spreadsheet formula",
            },
            {
                "created_at": "2026-01-01T00:20:00Z",
                "event_type": "objective_assessed",
                "title": "Assessment",
                "detail": "Effective",
            },
        ]

    def chaos_state(self) -> dict:
        return {
            "runs": [
                {
                    "id": "run_degrade",
                    "action": "app_degradation",
                    "intensity": "medium",
                    "pattern": "ramp",
                    "status": "completed",
                    "duration_seconds": 60,
                    "started_at": "2026-01-01T00:00:00Z",
                    "ended_at": "2026-01-01T00:01:00Z",
                    "reason": "duration_elapsed",
                    "artifacts": ["artifacts/degradation.md"],
                    "observations": [
                        {
                            "snapshot": {
                                "conditions": {
                                    "latency_ms": 2500,
                                    "error_rate": 0.2,
                                }
                            }
                        }
                    ],
                },
                {
                    "id": "run_dns",
                    "action": "dns_failure",
                    "intensity": "high",
                    "pattern": "flap",
                    "status": "aborted",
                    "duration_seconds": 60,
                    "started_at": "2026-01-01T00:02:00Z",
                    "ended_at": "2026-01-01T00:02:20Z",
                    "reason": "guardrail:target_unreachable",
                    "artifacts": [],
                    "observations": [
                        {
                            "snapshot": {
                                "conditions": {
                                    "dns_failure_rate": 0.8,
                                }
                            }
                        }
                    ],
                },
            ],
            "playbook_runs": [
                {
                    "id": "pbr_test",
                    "name": "Scenario Cascade",
                    "status": "completed",
                    "seed": 42,
                }
            ],
        }
