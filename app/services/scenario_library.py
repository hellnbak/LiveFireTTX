from __future__ import annotations

from hashlib import sha256
from typing import Any, Iterable
import json
import re

from app.models import (
    Exercise,
    ExerciseCheckpoint,
    ExerciseCreate,
    InjectOption,
    OrganizationProfile,
    SCENARIO_LIBRARY,
    ScenarioPack,
    create_checkpoint,
    find_organization_profile,
    find_scenario_pack,
    get_organization_profile,
    list_organization_profiles,
    list_scenario_packs,
    new_id,
    save_organization_profile,
    save_scenario_pack,
    timestamp,
)
from app.services.artifacts import ARTIFACT_KINDS, create_safe_artifact_inject
from app.services.generator import create_exercise_from_request, render_exercise_package


PACK_SCHEMA_VERSION = 1
PACK_MEDIA_TYPE = "application/vnd.livefirettx.scenario-pack+json"
PROFILE_MEDIA_TYPE = "application/vnd.livefirettx.organization-profile+json"
MAX_IMPORT_CHARACTERS = 256 * 1024
SLUG_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{1,63}")
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?")
STAGE_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
BUILTIN_ARTIFACTS = {"artifacts/customer_complaint.md"}


def seed_builtin_scenario_packs() -> list[ScenarioPack]:
    seeded = []
    for slug, scenario in SCENARIO_LIBRARY.items():
        definition = {
            "schema_version": PACK_SCHEMA_VERSION,
            "slug": slug.replace("_", "-"),
            "name": scenario["label"],
            "version": "1.0.0",
            "description": scenario["description"],
            "base_scenario_type": slug,
            "defaults": {
                "business_system": scenario["default_business_system"],
                "difficulty": scenario["default_difficulty"],
                "duration_minutes": scenario["default_duration_minutes"],
                "participants": scenario["recommended_roles"],
                "objectives": scenario["default_objectives"],
            },
            "injects": [],
            "checkpoints": [],
        }
        seeded.append(create_scenario_pack(definition, source="builtin"))
    return seeded


def create_scenario_pack(
    definition: dict[str, Any],
    *,
    source: str,
) -> ScenarioPack:
    normalized = validate_scenario_pack(definition)
    checksum = _checksum(normalized)
    existing = find_scenario_pack(normalized["slug"], normalized["version"])
    if existing:
        if existing.checksum != checksum:
            raise ValueError("Scenario pack version already exists with different content")
        return existing
    pack = ScenarioPack(
        id=new_id("spk"),
        slug=normalized["slug"],
        name=normalized["name"],
        version=normalized["version"],
        description=normalized["description"],
        base_scenario_type=normalized["base_scenario_type"],
        definition=normalized,
        checksum=checksum,
        source=source,
        created_at=timestamp(),
    )
    save_scenario_pack(pack)
    return pack


def import_scenario_pack(payload: str) -> ScenarioPack:
    if not payload or len(payload) > MAX_IMPORT_CHARACTERS:
        raise ValueError("Scenario pack import must be 1 to 262144 characters")
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("Scenario pack must be valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("Scenario pack must be a JSON object")
    return create_scenario_pack(decoded, source="import")


def export_scenario_pack(pack: ScenarioPack) -> str:
    return json.dumps(pack.definition, indent=2, sort_keys=True) + "\n"


def capture_exercise_as_pack(
    exercise: Exercise,
    injects: Iterable[InjectOption],
    checkpoints: Iterable[ExerciseCheckpoint],
    *,
    slug: str,
    name: str,
    version: str,
    description: str,
) -> ScenarioPack:
    portable_injects = []
    for inject in injects:
        portable = _portable_inject(inject)
        if portable:
            portable_injects.append(portable)
    definition = {
        "schema_version": PACK_SCHEMA_VERSION,
        "slug": slug,
        "name": name,
        "version": version,
        "description": description,
        "base_scenario_type": exercise.scenario_type,
        "defaults": {
            "business_system": exercise.business_system,
            "difficulty": exercise.difficulty,
            "duration_minutes": exercise.duration_minutes,
            "participants": exercise.participants,
            "objectives": exercise.objectives,
        },
        "injects": portable_injects,
        "checkpoints": [
            {
                "title": checkpoint.title,
                "description": checkpoint.description,
                "audience": checkpoint.audience,
                "expected_action": checkpoint.expected_action,
                "scheduled_offset_seconds": checkpoint.scheduled_offset_seconds,
                "objective_index": checkpoint.objective_index,
            }
            for checkpoint in checkpoints
        ],
    }
    return create_scenario_pack(definition, source="exercise")


def validate_scenario_pack(definition: dict[str, Any]) -> dict[str, Any]:
    if definition.get("schema_version") != PACK_SCHEMA_VERSION:
        raise ValueError("Unsupported scenario pack schema version")
    slug = _slug(definition.get("slug"), "Scenario pack slug")
    name = _single_line(definition.get("name"), "Scenario pack name", 120)
    version = _version(definition.get("version"))
    description = _text(definition.get("description"), "Description", 1000)
    base_scenario_type = str(definition.get("base_scenario_type", ""))
    if base_scenario_type not in SCENARIO_LIBRARY:
        raise ValueError("Scenario pack has an unknown base scenario type")
    defaults = _normalize_defaults(definition.get("defaults"), base_scenario_type)
    injects_value = definition.get("injects", [])
    checkpoints_value = definition.get("checkpoints", [])
    if not isinstance(injects_value, list) or len(injects_value) > 100:
        raise ValueError("Scenario pack injects must be a list of at most 100 items")
    if not isinstance(checkpoints_value, list) or len(checkpoints_value) > 50:
        raise ValueError("Scenario pack checkpoints must be a list of at most 50 items")
    injects = [
        _normalize_inject(item, base_scenario_type)
        for item in injects_value
    ]
    checkpoints = [
        _normalize_checkpoint(item, len(defaults["objectives"]))
        for item in checkpoints_value
    ]
    return {
        "schema_version": PACK_SCHEMA_VERSION,
        "slug": slug,
        "name": name,
        "version": version,
        "description": description,
        "base_scenario_type": base_scenario_type,
        "defaults": defaults,
        "injects": injects,
        "checkpoints": checkpoints,
    }


def instantiate_scenario_pack(
    pack: ScenarioPack,
    *,
    exercise_name: str,
    organization_profile_id: str | None = None,
) -> tuple[Exercise, list[InjectOption]]:
    definition = validate_scenario_pack(pack.definition)
    defaults = definition["defaults"]
    profile = (
        get_organization_profile(organization_profile_id)
        if organization_profile_id
        else None
    )
    if organization_profile_id and not profile:
        raise ValueError("Organization profile was not found")
    request = ExerciseCreate(
        name=_single_line(exercise_name, "Exercise name", 120),
        scenario_type=definition["base_scenario_type"],
        business_system=(
            profile.business_system if profile else defaults["business_system"]
        ),
        difficulty=defaults["difficulty"],
        duration_minutes=defaults["duration_minutes"],
        participants=(profile.participants if profile else defaults["participants"]),
        objectives=(profile.objectives if profile else defaults["objectives"]),
    )
    exercise, generated_injects = create_exercise_from_request(
        request,
        scenario_pack_id=pack.id,
        organization_profile_id=profile.id if profile else None,
    )
    if not definition["injects"]:
        render_exercise_package(exercise, generated_injects)
        return exercise, generated_injects
    generated_chaos = {
        inject.payload.get("action"): inject
        for inject in generated_injects
        if inject.action_type == "chaos_script"
    }
    injects = [
        _instantiate_inject(exercise, item, generated_chaos)
        for item in definition["injects"]
    ]
    render_exercise_package(exercise, injects)
    return exercise, injects


def create_pack_checkpoints(pack: ScenarioPack, exercise: Exercise) -> int:
    checkpoints = validate_scenario_pack(pack.definition)["checkpoints"]
    for item in checkpoints:
        create_checkpoint(exercise.id, **item)
    return len(checkpoints)


def create_organization_profile(
    *,
    slug: str,
    name: str,
    version: str,
    description: str,
    business_system: str,
    participants: Iterable[str],
    objectives: Iterable[str],
) -> OrganizationProfile:
    normalized_slug = _slug(slug, "Organization profile slug")
    normalized_version = _version(version)
    existing = find_organization_profile(normalized_slug, normalized_version)
    if existing:
        raise ValueError("Organization profile version already exists")
    profile = OrganizationProfile(
        id=new_id("org"),
        slug=normalized_slug,
        name=_single_line(name, "Organization profile name", 120),
        version=normalized_version,
        description=_text(description, "Description", 1000),
        business_system=_single_line(
            business_system,
            "Business system",
            120,
        ),
        participants=_string_list(participants, "Participants", 25, 120),
        objectives=_string_list(objectives, "Objectives", 20, 240),
        created_at=timestamp(),
    )
    save_organization_profile(profile)
    return profile


def latest_scenario_packs() -> list[ScenarioPack]:
    return _latest_versions(list_scenario_packs())


def latest_organization_profiles() -> list[OrganizationProfile]:
    return _latest_versions(list_organization_profiles())


def organization_profile_payload(profile: OrganizationProfile) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "slug": profile.slug,
        "name": profile.name,
        "version": profile.version,
        "description": profile.description,
        "business_system": profile.business_system,
        "participants": profile.participants,
        "objectives": profile.objectives,
    }


def _normalize_defaults(value: Any, scenario_type: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Scenario pack defaults must be an object")
    scenario = SCENARIO_LIBRARY[scenario_type]
    difficulty = str(value.get("difficulty", scenario["default_difficulty"]))
    if difficulty not in {"beginner", "intermediate", "advanced"}:
        raise ValueError("Scenario pack difficulty is invalid")
    duration = value.get("duration_minutes", scenario["default_duration_minutes"])
    if not isinstance(duration, int) or isinstance(duration, bool) or not 15 <= duration <= 480:
        raise ValueError("Scenario pack duration must be between 15 and 480 minutes")
    return {
        "business_system": _single_line(
            value.get("business_system", scenario["default_business_system"]),
            "Business system",
            120,
        ),
        "difficulty": difficulty,
        "duration_minutes": duration,
        "participants": _string_list(
            value.get("participants", scenario["recommended_roles"]),
            "Participants",
            25,
            120,
        ),
        "objectives": _string_list(
            value.get("objectives", scenario["default_objectives"]),
            "Objectives",
            20,
            240,
        ),
    }


def _normalize_inject(value: Any, scenario_type: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Each scenario pack inject must be an object")
    action_type = str(value.get("action_type", ""))
    if action_type not in {"narrative", "chaos_script", "artifact"}:
        raise ValueError("Scenario pack inject type is invalid")
    stage = str(value.get("stage", "")).strip()
    if not STAGE_PATTERN.fullmatch(stage):
        raise ValueError("Scenario pack inject stage is invalid")
    scheduled = value.get("scheduled_offset_seconds")
    if scheduled is not None and (
        not isinstance(scheduled, int)
        or isinstance(scheduled, bool)
        or not 0 <= scheduled <= 28800
    ):
        raise ValueError("Scenario pack inject schedule is invalid")
    normalized: dict[str, Any] = {
        "stage": stage,
        "title": _single_line(value.get("title"), "Inject title", 120),
        "audience": _single_line(value.get("audience"), "Inject audience", 120),
        "description": _text(value.get("description"), "Inject description", 2000),
        "action_type": action_type,
        "scheduled_offset_seconds": scheduled,
        "auto_deliver": bool(value.get("auto_deliver", False)),
    }
    if normalized["auto_deliver"] and action_type != "narrative":
        raise ValueError("Only narrative injects can be delivered automatically")
    if action_type == "chaos_script":
        action = str(value.get("action", ""))
        if action not in SCENARIO_LIBRARY[scenario_type]["chaos_modules"]:
            raise ValueError("Scenario pack chaos action is not allowed by its base")
        normalized["action"] = action
    elif action_type == "narrative":
        payload = value.get("payload", {})
        if not isinstance(payload, dict):
            raise ValueError("Narrative inject payload must be an object")
        encoded = json.dumps(payload)
        if len(encoded) > 4096:
            raise ValueError("Narrative inject payload is too large")
        normalized["payload"] = json.loads(encoded)
    else:
        artifact_kind = value.get("artifact_kind")
        content = value.get("content")
        artifact_path = value.get("artifact_path")
        if artifact_kind is not None or content is not None:
            if artifact_kind not in ARTIFACT_KINDS:
                raise ValueError("Scenario pack artifact type is invalid")
            normalized["artifact_kind"] = artifact_kind
            normalized["content"] = _text(content, "Artifact content", 10000)
        elif artifact_path not in BUILTIN_ARTIFACTS:
            raise ValueError("Scenario pack artifact path is not portable")
        else:
            normalized["artifact_path"] = artifact_path
    return normalized


def _normalize_checkpoint(value: Any, objective_count: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Each scenario pack checkpoint must be an object")
    objective_index = value.get("objective_index")
    if objective_index is not None and (
        not isinstance(objective_index, int)
        or isinstance(objective_index, bool)
        or not 0 <= objective_index < objective_count
    ):
        raise ValueError("Scenario pack checkpoint objective is invalid")
    scheduled = value.get("scheduled_offset_seconds")
    if (
        not isinstance(scheduled, int)
        or isinstance(scheduled, bool)
        or not 0 <= scheduled <= 28800
    ):
        raise ValueError("Scenario pack checkpoint schedule is invalid")
    return {
        "title": _single_line(value.get("title"), "Checkpoint title", 120),
        "description": _text(
            value.get("description"),
            "Checkpoint description",
            2000,
        ),
        "audience": _single_line(
            value.get("audience"),
            "Checkpoint audience",
            120,
        ),
        "expected_action": _text(
            value.get("expected_action"),
            "Expected action",
            2000,
        ),
        "scheduled_offset_seconds": scheduled,
        "objective_index": objective_index,
    }


def _portable_inject(inject: InjectOption) -> dict[str, Any] | None:
    portable: dict[str, Any] = {
        "stage": inject.stage,
        "title": inject.title,
        "audience": inject.audience,
        "description": inject.description,
        "action_type": inject.action_type,
        "scheduled_offset_seconds": inject.scheduled_offset_seconds,
        "auto_deliver": inject.auto_deliver,
    }
    if inject.action_type == "chaos_script":
        portable["action"] = inject.payload.get("action")
    elif inject.action_type == "narrative":
        portable["payload"] = inject.payload
    elif inject.payload.get("facilitator_defined"):
        content = inject.payload.get("content")
        if not isinstance(content, str) or not content.strip():
            return None
        portable["artifact_kind"] = inject.payload.get("artifact_kind")
        portable["content"] = content
    else:
        portable["artifact_path"] = inject.payload.get("artifact")
    return portable


def _instantiate_inject(
    exercise: Exercise,
    definition: dict[str, Any],
    generated_chaos: dict[Any, InjectOption],
) -> InjectOption:
    if definition["action_type"] == "artifact" and "artifact_kind" in definition:
        inject = create_safe_artifact_inject(
            exercise,
            definition["title"],
            definition["audience"],
            definition["stage"],
            definition["artifact_kind"],
            definition["content"],
        )
        inject.description = definition["description"]
    else:
        payload: dict[str, Any]
        script_name = None
        if definition["action_type"] == "chaos_script":
            generated = generated_chaos.get(definition["action"])
            if not generated:
                raise ValueError("Scenario pack chaos action is unavailable")
            payload = dict(generated.payload)
            script_name = generated.script_name
        elif definition["action_type"] == "artifact":
            payload = {"artifact": definition["artifact_path"]}
        else:
            payload = dict(definition.get("payload", {}))
        inject = InjectOption(
            id=new_id("inj"),
            exercise_id=exercise.id,
            stage=definition["stage"],
            title=definition["title"],
            audience=definition["audience"],
            description=definition["description"],
            action_type=definition["action_type"],
            script_name=script_name,
            payload=payload,
        )
    inject.scheduled_offset_seconds = definition["scheduled_offset_seconds"]
    inject.auto_deliver = definition["auto_deliver"]
    return inject


def _latest_versions(items: Iterable[Any]) -> list[Any]:
    latest: dict[str, Any] = {}
    for item in items:
        current = latest.get(item.slug)
        if current is None or _version_key(item.version) > _version_key(
            current.version
        ):
            latest[item.slug] = item
    return sorted(latest.values(), key=lambda item: item.name.lower())


def _version_key(version: str) -> tuple[int, int, int, int, str]:
    core, _, suffix = version.partition("-")
    major, minor, patch = (int(part) for part in core.split("."))
    return major, minor, patch, 1 if not suffix else 0, suffix


def _checksum(definition: dict[str, Any]) -> str:
    canonical = json.dumps(
        definition,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256(canonical).hexdigest()


def _slug(value: Any, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not SLUG_PATTERN.fullmatch(normalized):
        raise ValueError(f"{label} must use lowercase letters, numbers, and hyphens")
    return normalized


def _version(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not VERSION_PATTERN.fullmatch(normalized):
        raise ValueError("Version must use semantic version format such as 1.0.0")
    return normalized


def _single_line(value: Any, label: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if (
        not normalized
        or len(normalized) > maximum
        or "\n" in normalized
        or "\r" in normalized
    ):
        raise ValueError(
            f"{label} must be a single line between 1 and {maximum} characters"
        )
    return normalized


def _text(value: Any, label: str, maximum: int) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{label} must be between 1 and {maximum} characters")
    return normalized


def _string_list(
    values: Any,
    label: str,
    maximum_items: int,
    maximum_length: int,
) -> list[str]:
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{label} must be a list")
    normalized = [
        _single_line(item, label.removesuffix("s"), maximum_length)
        for item in values
    ]
    if not normalized or len(normalized) > maximum_items:
        raise ValueError(f"{label} must contain 1 to {maximum_items} items")
    return normalized
