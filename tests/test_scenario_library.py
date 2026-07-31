from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import json

from app import models
from app.services.operations import seed_default_checkpoints
from app.services.scenario_library import (
    capture_exercise_as_pack,
    create_organization_profile,
    export_scenario_pack,
    import_scenario_pack,
    instantiate_scenario_pack,
    latest_organization_profiles,
    latest_scenario_packs,
    seed_builtin_scenario_packs,
    validate_scenario_pack,
)


class ScenarioLibraryTests(TestCase):
    def test_documented_example_is_valid(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "scenario-pack-example.json"
        normalized = validate_scenario_pack(json.loads(example.read_text()))
        self.assertEqual("cloud_outage", normalized["base_scenario_type"])
        self.assertEqual(2, len(normalized["injects"]))

    def test_exports_portable_design_and_recreates_exercise(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(models, "DB_PATH", root / "livefirettx.db"),
                patch.object(models, "GENERATED_ROOT", root / "exercises"),
                patch(
                    "app.services.generator.GENERATED_ROOT",
                    root / "exercises",
                ),
            ):
                models.init_db()
                packs = seed_builtin_scenario_packs()
                cloud_pack = next(
                    item for item in packs if item.base_scenario_type == "cloud_outage"
                )
                profile = create_organization_profile(
                    slug="commerce-operations",
                    name="Commerce Operations",
                    version="1.0.0",
                    description="Commerce incident organization context.",
                    business_system="Checkout Platform",
                    participants=["Incident Commander", "SRE"],
                    objectives=["Assess impact", "Recover service"],
                )
                exercise, injects = instantiate_scenario_pack(
                    cloud_pack,
                    exercise_name="Portable cloud exercise",
                    organization_profile_id=profile.id,
                )
                models.save_exercise(exercise)
                models.save_injects(injects)
                checkpoints = seed_default_checkpoints(exercise)

                captured = capture_exercise_as_pack(
                    exercise,
                    injects,
                    checkpoints,
                    slug="portable-cloud-response",
                    name="Portable Cloud Response",
                    version="2.1.0",
                    description="Reusable cloud response design.",
                )
                exported = export_scenario_pack(captured)
                payload = json.loads(exported)

                self.assertNotIn(exercise.id, exported)
                self.assertNotIn(exercise.package_path, exported)
                self.assertNotIn("triggered", exported)
                self.assertEqual("cloud_outage", payload["base_scenario_type"])
                self.assertEqual(len(injects), len(payload["injects"]))
                self.assertEqual(len(checkpoints), len(payload["checkpoints"]))
                self.assertEqual(captured.id, import_scenario_pack(exported).id)

                recreated, recreated_injects = instantiate_scenario_pack(
                    captured,
                    exercise_name="Recreated portable exercise",
                )
                self.assertEqual(captured.id, recreated.scenario_pack_id)
                self.assertNotEqual(exercise.id, recreated.id)
                self.assertEqual(len(injects), len(recreated_injects))
                exercise_definition = Path(
                    recreated.package_path,
                    "exercise.yml",
                ).read_text()
                self.assertIn(captured.id, exercise_definition)

    def test_rejects_unallowlisted_action_and_conflicting_versions(self) -> None:
        with TemporaryDirectory() as temporary:
            with patch.object(
                models,
                "DB_PATH",
                Path(temporary) / "livefirettx.db",
            ):
                models.init_db()
                pack = seed_builtin_scenario_packs()[0]
                payload = json.loads(export_scenario_pack(pack))
                payload["injects"] = [
                    {
                        "stage": "01-test",
                        "title": "Unsafe action",
                        "audience": "Facilitator",
                        "description": "Must be rejected.",
                        "action_type": "chaos_script",
                        "scheduled_offset_seconds": None,
                        "auto_deliver": False,
                        "action": "shell_command",
                    }
                ]
                with self.assertRaisesRegex(ValueError, "not allowed"):
                    import_scenario_pack(json.dumps(payload))

                create_organization_profile(
                    slug="security-operations",
                    name="Security Operations",
                    version="1.0.0",
                    description="Security response profile.",
                    business_system="Security Platform",
                    participants=["Incident Commander"],
                    objectives=["Coordinate response"],
                )
                with self.assertRaisesRegex(ValueError, "already exists"):
                    create_organization_profile(
                        slug="security-operations",
                        name="Security Operations Updated",
                        version="1.0.0",
                        description="Conflicting immutable profile.",
                        business_system="Security Platform",
                        participants=["Incident Commander"],
                        objectives=["Coordinate response"],
                    )
                self.assertEqual(6, len(latest_scenario_packs()))
                self.assertEqual(1, len(latest_organization_profiles()))
