# Copyright (c) 2026 Steve Manzuik
# Licensed under FSL-1.1-ALv2. See LICENSE.

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent
import re

from app.models import Exercise, InjectOption, new_id


ARTIFACT_KINDS = {
    "executive_email": {
        "label": "Executive Email",
        "description": "A simulated executive request or status escalation.",
    },
    "customer_message": {
        "label": "Customer Message",
        "description": "A simulated customer complaint or support escalation.",
    },
    "security_alert": {
        "label": "Security Alert",
        "description": "A clearly labeled synthetic detection or monitoring alert.",
    },
    "service_ticket": {
        "label": "Service Ticket",
        "description": "A simulated operational, vendor, or support ticket.",
    },
    "vendor_advisory": {
        "label": "Vendor Advisory",
        "description": "A simulated third-party notice or dependency advisory.",
    },
}


def create_safe_artifact_inject(
    exercise: Exercise,
    title: str,
    audience: str,
    stage: str,
    artifact_kind: str,
    content: str,
) -> InjectOption:
    title = _single_line(title, "Artifact title", 120)
    audience = _single_line(audience, "Artifact audience", 120)
    stage = stage.strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", stage):
        raise ValueError("Stage must use lowercase letters, numbers, _ or -")
    if artifact_kind not in ARTIFACT_KINDS:
        raise ValueError("Unknown safe artifact type")
    content = content.strip()
    if not content or len(content) > 10000:
        raise ValueError("Artifact content must be between 1 and 10000 characters")

    inject_id = new_id("inj")
    package_root = Path(exercise.package_path).resolve()
    artifacts_root = (package_root / "artifacts").resolve()
    if package_root not in artifacts_root.parents:
        raise ValueError("Exercise artifact directory resolves outside the package")
    artifact_root = artifacts_root / "facilitator"
    artifact_root.mkdir(parents=True, exist_ok=True)
    artifact_root = artifact_root.resolve()
    if artifacts_root not in artifact_root.parents:
        raise ValueError("Facilitator artifact directory resolves outside the package")
    artifact_path = artifact_root / f"{inject_id}_{artifact_kind}.md"
    kind = ARTIFACT_KINDS[artifact_kind]
    artifact_path.write_text(
        dedent(
            f"""\
            # SIMULATED EXERCISE ARTIFACT

            > LiveFireTTX training material. This is not a real message, alert,
            > ticket, or advisory.

            ## {title}

            - Type: {kind['label']}
            - Intended audience: {audience}
            - Exercise: {exercise.name}
            - Business system: {exercise.business_system}
            - Created: {datetime.now(timezone.utc).isoformat()}

            ## Inject Content

            {content}

            ---

            **SIMULATED EXERCISE ARTIFACT — DO NOT TREAT AS A REAL INCIDENT RECORD**
            """
        )
    )
    relative_path = artifact_path.relative_to(package_root)
    return InjectOption(
        id=inject_id,
        exercise_id=exercise.id,
        stage=stage,
        title=title,
        audience=audience,
        description=kind["description"],
        action_type="artifact",
        script_name=None,
        payload={
            "artifact": str(relative_path),
            "artifact_kind": artifact_kind,
            "safe": True,
            "facilitator_defined": True,
        },
    )


def artifact_trigger_result(exercise: Exercise, inject: InjectOption) -> str:
    relative_path = str(inject.payload.get("artifact", ""))
    package_root = Path(exercise.package_path).resolve()
    artifact_path = (package_root / relative_path).resolve()
    artifact_root = (package_root / "artifacts").resolve()
    if (
        package_root not in artifact_root.parents
        or artifact_root not in artifact_path.parents
        or not artifact_path.is_file()
    ):
        raise ValueError("Artifact file is unavailable or outside the exercise package")
    return f"Prepared safe exercise artifact: {relative_path}"


def _single_line(value: str, label: str, maximum: int) -> str:
    normalized = value.strip()
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
