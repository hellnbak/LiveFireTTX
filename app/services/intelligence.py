# Copyright (c) 2026 Steve Manzuik
# Licensed under FSL-1.1-ALv2. See LICENSE.

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO, StringIO
from typing import Any, Iterable
from zipfile import ZIP_DEFLATED, ZipFile
import csv
import json

from app.models import Exercise, InjectOption


RATING_SCORES = {
    "not_assessed": 0,
    "developing": 1,
    "effective": 2,
    "exemplary": 3,
}
RATING_LABELS = {
    "not_assessed": "Not assessed",
    "developing": "Developing",
    "effective": "Effective",
    "exemplary": "Exemplary",
}


def build_exercise_intelligence(
    exercise: Exercise,
    injects: list[InjectOption],
    events: Iterable[Any],
    chaos_state: dict[str, Any] | None,
    assessments: Iterable[Any],
) -> dict[str, Any]:
    state = chaos_state or {}
    event_rows = [_row_dict(event) for event in events]
    assessment_rows = {
        int(_row_value(row, "objective_index")): _row_dict(row)
        for row in assessments
    }
    objectives = []
    assessed_count = 0
    earned_points = 0
    for index, objective in enumerate(exercise.objectives):
        assessment = assessment_rows.get(index, {})
        rating = assessment.get("rating", "not_assessed")
        if rating not in RATING_SCORES:
            rating = "not_assessed"
        score = RATING_SCORES[rating]
        if rating != "not_assessed":
            assessed_count += 1
        earned_points += score
        objectives.append(
            {
                "index": index,
                "objective": objective,
                "rating": rating,
                "rating_label": RATING_LABELS[rating],
                "score": score,
                "notes": assessment.get("notes", ""),
                "updated_at": assessment.get("updated_at"),
            }
        )

    total_objective_points = max(1, len(objectives) * 3)
    objective_score = round((earned_points / total_objective_points) * 100)
    triggered_injects = sum(1 for inject in injects if inject.triggered)
    inject_coverage = round(
        (triggered_injects / max(1, len(injects))) * 100
    )

    chaos_runs = state.get("runs", [])
    terminal_runs = [
        run
        for run in chaos_runs
        if run.get("status") in {"completed", "aborted", "failed"}
    ]
    safely_terminated = [
        run
        for run in terminal_runs
        if run.get("status") in {"completed", "aborted"}
    ]
    safe_run_rate = round(
        (len(safely_terminated) / max(1, len(terminal_runs))) * 100
    )
    evidence_events = [
        event
        for event in event_rows
        if event.get("event_type") != "exercise_created"
    ]
    documentation_score = min(
        100,
        round(
            (len(evidence_events) / max(1, len(exercise.objectives))) * 100
        ),
    )
    readiness_score = round(
        objective_score * 0.55
        + inject_coverage * 0.15
        + safe_run_rate * 0.15
        + documentation_score * 0.15
    )
    guardrail_stops = sum(
        1
        for run in chaos_runs
        if str(run.get("reason", "")).startswith("guardrail:")
    )
    playbook_runs = state.get("playbook_runs", [])
    run_comparison = [
        summarize_run(run)
        for run in reversed(chaos_runs[-12:])
    ]

    return {
        "readiness_score": readiness_score,
        "score_label": score_label(readiness_score),
        "assessment_complete": (
            bool(objectives) and assessed_count == len(objectives)
        ),
        "assessed_objectives": assessed_count,
        "objective_count": len(objectives),
        "objective_score": objective_score,
        "objectives": objectives,
        "inject_coverage": inject_coverage,
        "triggered_injects": triggered_injects,
        "inject_count": len(injects),
        "safe_run_rate": safe_run_rate,
        "terminal_run_count": len(terminal_runs),
        "documentation_score": documentation_score,
        "evidence_event_count": len(evidence_events),
        "guardrail_stops": guardrail_stops,
        "chaos_run_count": len(chaos_runs),
        "playbook_run_count": len(playbook_runs),
        "completed_playbooks": sum(
            1 for run in playbook_runs if run.get("status") == "completed"
        ),
        "run_comparison": run_comparison,
    }


def summarize_run(run: dict[str, Any]) -> dict[str, Any]:
    peak = peak_conditions(run)
    impact_score = min(
        100,
        round(
            min(1, peak["latency_ms"] / 5000) * 35
            + peak["error_rate"] * 25
            + peak["auth_failure_rate"] * 20
            + peak["dns_failure_rate"] * 20
        ),
    )
    return {
        "id": run.get("id"),
        "action": run.get("action", "unknown"),
        "intensity": run.get("intensity", "medium"),
        "pattern": run.get("pattern", "steady"),
        "status": run.get("status", "pending"),
        "reason": run.get("reason", ""),
        "duration_seconds": run.get("duration_seconds"),
        "elapsed_seconds": elapsed_seconds(run),
        "impact_score": impact_score,
        "peak_conditions": peak,
        "observation_count": len(run.get("observations", [])),
        "playbook_run_id": run.get("playbook_run_id"),
    }


def peak_conditions(run: dict[str, Any]) -> dict[str, float]:
    peak = {
        "latency_ms": 0,
        "error_rate": 0.0,
        "auth_failure_rate": 0.0,
        "dns_failure_rate": 0.0,
    }
    snapshots = [
        run.get("before_snapshot"),
        run.get("after_snapshot"),
        *[
            observation.get("snapshot")
            for observation in run.get("observations", [])
        ],
    ]
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            continue
        conditions = snapshot.get("conditions", {})
        for field in peak:
            try:
                peak[field] = max(peak[field], float(conditions.get(field, 0)))
            except (TypeError, ValueError):
                continue
    peak["latency_ms"] = round(peak["latency_ms"])
    for field in {"error_rate", "auth_failure_rate", "dns_failure_rate"}:
        peak[field] = round(peak[field], 4)
    return peak


def elapsed_seconds(run: dict[str, Any]) -> int | None:
    started_at = _parse_timestamp(run.get("started_at"))
    ended_at = _parse_timestamp(run.get("ended_at"))
    if not started_at:
        return None
    if not ended_at and run.get("status") == "active":
        ended_at = datetime.now(timezone.utc)
    if not ended_at:
        return None
    return max(0, round((ended_at - started_at).total_seconds()))


def score_label(score: int) -> str:
    if score >= 85:
        return "Exercise ready"
    if score >= 65:
        return "Operational"
    if score >= 40:
        return "Developing"
    return "Needs assessment"


def render_evidence_markdown(
    exercise: Exercise,
    intelligence: dict[str, Any],
    events: Iterable[Any],
    chaos_state: dict[str, Any] | None,
) -> str:
    state = chaos_state or {}
    lines = [
        f"# After Action Evidence: {exercise.name}",
        "",
        "## Exercise Metadata",
        f"- Exercise ID: {exercise.id}",
        f"- Scenario: {exercise.scenario_type}",
        f"- Business system: {exercise.business_system}",
        f"- Planned duration: {exercise.duration_minutes} minutes",
        f"- Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Readiness Summary",
        f"- Provisional readiness score: {intelligence['readiness_score']}/100",
        f"- Objective assessment: {intelligence['objective_score']}%",
        f"- Inject coverage: {intelligence['inject_coverage']}%",
        f"- Safe run termination: {intelligence['safe_run_rate']}%",
        f"- Evidence documentation: {intelligence['documentation_score']}%",
        "",
        "## Objective Assessments",
    ]
    for objective in intelligence["objectives"]:
        lines.extend(
            [
                (
                    f"### {objective['index'] + 1}. "
                    f"{objective['objective']}"
                ),
                f"- Rating: {objective['rating_label']}",
                f"- Score: {objective['score']}/3",
                f"- Notes: {objective['notes'] or '_No notes recorded._'}",
                "",
            ]
        )

    lines.append("## Chaos Run Comparison")
    if intelligence["run_comparison"]:
        lines.extend(
            [
                "| Action | Status | Intensity | Pattern | Impact | Peak latency | Peak error |",
                "|---|---|---|---|---:|---:|---:|",
            ]
        )
        for run in intelligence["run_comparison"]:
            peak = run["peak_conditions"]
            lines.append(
                f"| {run['action']} | {run['status']} | "
                f"{run['intensity']} | {run['pattern']} | "
                f"{run['impact_score']} | {peak['latency_ms']} ms | "
                f"{peak['error_rate']:.1%} |"
            )
    else:
        lines.append("_No chaos runs recorded._")

    lines.extend(["", "## Playbook Runs"])
    playbook_runs = state.get("playbook_runs", [])
    if playbook_runs:
        for run in reversed(playbook_runs):
            lines.append(
                f"- {run.get('name', run.get('playbook_id'))}: "
                f"{run.get('status')} (seed {run.get('seed')})"
            )
    else:
        lines.append("_No playbook runs recorded._")

    lines.extend(["", "## Facilitator Timeline"])
    event_rows = sorted(
        (_row_dict(event) for event in events),
        key=lambda event: event.get("created_at", ""),
    )
    if event_rows:
        for event in event_rows:
            detail = str(event.get("detail", "")).replace("\n", " — ")
            lines.append(
                f"- **{event.get('created_at')}** "
                f"[{event.get('event_type')}] {event.get('title')}: {detail}"
            )
    else:
        lines.append("_No facilitator events recorded._")

    lines.extend(["", "## Evidence Artifacts"])
    artifacts = sorted(
        {
            artifact
            for run in state.get("runs", [])
            for artifact in run.get("artifacts", [])
        }
    )
    if artifacts:
        lines.extend(f"- {artifact}" for artifact in artifacts)
    else:
        lines.append("_No generated artifacts recorded._")
    lines.append("")
    return "\n".join(lines)


def build_evidence_archive(
    exercise: Exercise,
    intelligence: dict[str, Any],
    events: Iterable[Any],
    chaos_state: dict[str, Any] | None,
) -> bytes:
    state = chaos_state or {}
    event_rows = [_row_dict(event) for event in events]
    markdown = render_evidence_markdown(
        exercise,
        intelligence,
        event_rows,
        state,
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("after_action_report.md", markdown)
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "exercise_id": exercise.id,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "files": [
                        "after_action_report.md",
                        "events.csv",
                        "chaos_runs.csv",
                        "objective_assessments.csv",
                        "chaos_state.json",
                    ],
                },
                indent=2,
            ),
        )
        archive.writestr(
            "events.csv",
            _csv_text(
                event_rows,
                ["created_at", "event_type", "title", "detail"],
            ),
        )
        archive.writestr(
            "chaos_runs.csv",
            _csv_text(
                intelligence["run_comparison"],
                [
                    "id",
                    "action",
                    "status",
                    "intensity",
                    "pattern",
                    "duration_seconds",
                    "elapsed_seconds",
                    "impact_score",
                    "observation_count",
                    "reason",
                    "playbook_run_id",
                ],
            ),
        )
        archive.writestr(
            "objective_assessments.csv",
            _csv_text(
                intelligence["objectives"],
                [
                    "index",
                    "objective",
                    "rating",
                    "rating_label",
                    "score",
                    "notes",
                    "updated_at",
                ],
            ),
        )
        archive.writestr(
            "chaos_state.json",
            json.dumps(state, indent=2, sort_keys=True),
        )
    return buffer.getvalue()


def _csv_text(rows: Iterable[dict[str, Any]], fields: list[str]) -> str:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(
        {
            field: _safe_csv_value(row.get(field))
            for field in fields
        }
        for row in rows
    )
    return stream.getvalue()


def _safe_csv_value(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped.startswith(("=", "+", "-", "@")) or value.startswith(
            ("\t", "\r", "\n")
        ):
            return f"'{value}"
    return value


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except (TypeError, ValueError):
        return {}


def _row_value(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (KeyError, TypeError):
        return None


def _parse_timestamp(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
