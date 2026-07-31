# Copyright (c) 2026 Steve Manzuik
# Licensed under FSL-1.1-ALv2. See LICENSE.

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse, urlsplit
import json
import logging
import uuid

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.models import (
    Exercise,
    ExerciseCreate,
    InjectOption,
    SCENARIO_LIBRARY,
    add_event,
    get_exercise,
    get_inject,
    get_injects,
    init_db,
    list_events,
    list_exercises,
    list_objective_assessments,
    mark_inject_triggered,
    save_objective_assessment,
    save_exercise,
    save_injects,
)
from app.routes.packages import router as packages_router
from app.routes.system import router as system_router
from app.services.artifacts import (
    ARTIFACT_KINDS,
    artifact_trigger_result,
    create_safe_artifact_inject,
)
from app.services.generator import create_exercise_from_request
from app.services.intelligence import (
    RATING_LABELS,
    RATING_SCORES,
    build_evidence_archive,
    build_exercise_intelligence,
    render_evidence_markdown,
)
from app.services.runtime import (
    ChaosExecutionError,
    ChaosPreflightError,
    clone_playbook_configuration,
    control_chaos_playbook_run,
    emergency_stop,
    export_playbook_configuration,
    read_chaos_state,
    read_control_status,
    read_dependency_status,
    read_playbook_configuration,
    read_playbook_definition,
    read_playbook_library,
    reset_chaos,
    restore_playbook_version,
    run_chaos_inject,
    save_playbook_configuration,
    skip_chaos_playbook_stage,
    start_chaos_playbook,
    validate_playbook_configuration,
)
from app.services.packages import (
    build_exercise_archive,
    dependency_map,
    list_participant_briefs,
)
from app.services.paths import (
    PackagePathError,
    exercise_package_path,
    validate_exercise_id,
)
from app.version import __version__

BASE = Path(__file__).resolve().parent
LOGGER = logging.getLogger("livefirettx")
if not LOGGER.handlers:
    log_handler = logging.StreamHandler()
    log_handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(log_handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
app = FastAPI(
    title="LiveFireTTX",
    version=__version__,
    description="Local-first live-fire tabletop exercise orchestration.",
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
)
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.globals["app_version"] = __version__
app.mount("/static", StaticFiles(directory=str(BASE / "templates" / "static")), name="static")
app.include_router(system_router)
app.include_router(packages_router)


@app.exception_handler(PackagePathError)
async def unsafe_package_path_handler(
    request: Request,
    error: PackagePathError,
) -> JSONResponse:
    LOGGER.warning(
        json.dumps(
            {
                "event": "unsafe_package_path_rejected",
                "path": request.url.path,
                "error_type": type(error).__name__,
            },
            sort_keys=True,
        )
    )
    return JSONResponse(
        {"detail": "Exercise package metadata is invalid"},
        status_code=409,
    )


async def _form_fields(
    request: Request,
    maximum_bytes: int = 64 * 1024,
) -> dict[str, str]:
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Expected URL-encoded form data")
    body = await request.body()
    if len(body) > maximum_bytes:
        raise HTTPException(413, "Form submission is too large")
    try:
        parsed = parse_qs(
            body.decode("utf-8"),
            keep_blank_values=True,
            max_num_fields=50,
            strict_parsing=False,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(400, "Form submission is invalid") from exc
    return {key: values[-1] for key, values in parsed.items() if values}


def _field(
    fields: dict[str, str],
    name: str,
    default: str | None = None,
) -> str:
    value = fields.get(name, default)
    if value is None:
        raise HTTPException(422, f"Missing form field: {name}")
    return value


def _integer_field(
    fields: dict[str, str],
    name: str,
    default: int,
) -> int:
    try:
        return int(_field(fields, name, str(default)))
    except ValueError as exc:
        raise HTTPException(422, f"{name} must be an integer") from exc


def _redirect_to_exercise(exercise: Exercise) -> RedirectResponse:
    exercise_id = validate_exercise_id(exercise.id)
    target = f"/exercises/{quote(exercise_id, safe='')}".replace("\\", "")
    parsed = urlparse(target)
    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path.startswith("/exercises/ttx_")
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        target = "/"
    return RedirectResponse(target, status_code=303)


def _same_local_origin(request: Request, origin: str) -> bool:
    try:
        candidate = urlsplit(origin)
        request_origin = urlsplit(
            f"{request.url.scheme}://{request.headers.get('host', '')}"
        )
        candidate_port = candidate.port or 80
        request_port = request_origin.port or 80
    except ValueError:
        return False
    return bool(
        candidate.scheme == request.url.scheme == "http"
        and candidate.hostname in LOOPBACK_HOSTS
        and request_origin.hostname in LOOPBACK_HOSTS
        and candidate_port == request_port
        and candidate.username is None
        and candidate.password is None
        and candidate.path in {"", "/"}
        and not candidate.query
        and not candidate.fragment
    )


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = uuid.uuid4().hex
    started = datetime.now(timezone.utc)
    origin = request.headers.get("origin")
    fetch_site = request.headers.get("sec-fetch-site", "").lower()
    opaque_same_origin = origin == "null" and fetch_site == "same-origin"
    if request.method in MUTATING_METHODS and (
        (
            origin is not None
            and not opaque_same_origin
            and not _same_local_origin(request, origin)
        )
        or (origin is None and fetch_site == "cross-site")
    ):
        LOGGER.warning(
            json.dumps(
                {
                    "event": "request_rejected",
                    "reason": "cross_origin_mutation",
                    "method": request.method,
                    "path": request.url.path,
                    "origin": origin,
                    "host": request.headers.get("host"),
                    "sec_fetch_site": fetch_site or None,
                },
                sort_keys=True,
            )
        )
        response = JSONResponse(
            {"detail": "Cross-origin state changes are not allowed"},
            status_code=403,
        )
    else:
        response = await call_next(request)
    completed = datetime.now(timezone.utc)
    elapsed_ms = round(
        (completed - started).total_seconds() * 1000,
        2,
    )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=()"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'; object-src 'none'; img-src 'self' data:; "
        "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'"
    )
    LOGGER.info(
        json.dumps(
            {
                "event": "request_completed",
                "timestamp": completed.isoformat(),
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "elapsed_ms": elapsed_ms,
            },
            sort_keys=True,
        )
    )
    return response


def _exercise_evidence(exercise):
    injects = get_injects(exercise.id)
    events = list_events(exercise.id)
    chaos_state = read_chaos_state(exercise)
    intelligence = build_exercise_intelligence(
        exercise,
        injects,
        events,
        chaos_state,
        list_objective_assessments(exercise.id),
    )
    return injects, events, chaos_state, intelligence


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "exercises": list_exercises(),
            "scenarios": SCENARIO_LIBRARY,
        },
    )


@app.get("/new", response_class=HTMLResponse)
def new_exercise(request: Request):
    return templates.TemplateResponse(
        request,
        "new.html",
        {"scenarios": SCENARIO_LIBRARY},
    )


@app.post("/exercises")
async def create_exercise(request: Request):
    fields = await _form_fields(request)
    name = _field(fields, "name")
    scenario_type = _field(fields, "scenario_type")
    platform = _field(fields, "platform", "local_docker")
    business_system = _field(fields, "business_system", "Order Processing")
    difficulty = _field(fields, "difficulty", "intermediate")
    duration_minutes = _integer_field(fields, "duration_minutes", 90)
    participants = _field(
        fields,
        "participants",
        (
            "Incident Commander, Security Operations, Cloud/IT Operations, "
            "Communications, Business Owner"
        ),
    )
    objectives = _field(fields, "objectives", "")
    name = name.strip()
    business_system = business_system.strip()
    if not name or len(name) > 120:
        raise HTTPException(400, "Exercise name must be between 1 and 120 characters")
    if scenario_type not in SCENARIO_LIBRARY:
        raise HTTPException(400, "Unknown scenario type")
    if platform != "local_docker":
        raise HTTPException(400, "Only the local Docker platform is currently supported")
    if difficulty not in {"beginner", "intermediate", "advanced"}:
        raise HTTPException(400, "Unknown difficulty")
    if not 15 <= duration_minutes <= 480:
        raise HTTPException(400, "Duration must be between 15 and 480 minutes")
    if not business_system or len(business_system) > 120:
        raise HTTPException(400, "Business system must be between 1 and 120 characters")

    participant_list = [p.strip() for p in participants.split(",") if p.strip()]
    objective_list = [o.strip() for o in objectives.split("\n") if o.strip()]
    if len(participant_list) > 25 or any(len(item) > 120 for item in participant_list):
        raise HTTPException(400, "Participant list is too large")
    if len(objective_list) > 20 or any(len(item) > 240 for item in objective_list):
        raise HTTPException(400, "Objective list is too large")

    req = ExerciseCreate(
        name=name,
        scenario_type=scenario_type,
        platform=platform,
        business_system=business_system,
        difficulty=difficulty,
        duration_minutes=duration_minutes,
        participants=participant_list,
        objectives=objective_list,
    )
    ex, injects = create_exercise_from_request(req)
    save_exercise(ex)
    save_injects(injects)
    add_event(
        ex.id,
        "exercise_created",
        "Exercise Created",
        "Generated the local exercise package",
    )
    return _redirect_to_exercise(ex)


@app.get("/exercises/{exercise_id}", response_class=HTMLResponse)
def exercise_detail(request: Request, exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    injects, events, chaos_state, intelligence = _exercise_evidence(ex)
    by_stage: dict[str, list[InjectOption]] = {}
    for i in injects:
        by_stage.setdefault(i.stage, []).append(i)
    chaos_actions = []
    known_actions = set()
    for inject in injects:
        action = inject.payload.get("action")
        if inject.action_type != "chaos_script" or not action:
            continue
        if action in known_actions:
            continue
        known_actions.add(action)
        chaos_actions.append({"id": action, "label": inject.title})
    playbook_library = read_playbook_library(ex)
    designer_playbook = (
        read_playbook_definition(ex, playbook_library[0]["id"])
        if playbook_library
        else {}
    )
    control_status = read_control_status(ex)
    dependencies: dict[str, Any] = (
        read_dependency_status(ex)
        if control_status.get("matches_exercise")
        else {"reachable": False, "dependencies": []}
    )
    dependency_status_by_id = {
        item.get("id"): item
        for item in dependencies.get("dependencies", [])
        if isinstance(item, dict)
    }
    return templates.TemplateResponse(
        request,
        "exercise.html",
        {
            "exercise": ex,
            "injects_by_stage": by_stage,
            "events": events,
            "chaos_state": chaos_state,
            "control_status": control_status,
            "playbook_configuration": read_playbook_configuration(ex),
            "playbook_library": playbook_library,
            "designer_playbook": designer_playbook,
            "chaos_actions": chaos_actions,
            "artifact_kinds": ARTIFACT_KINDS,
            "intelligence": intelligence,
            "rating_labels": RATING_LABELS,
            "scenario": SCENARIO_LIBRARY[ex.scenario_type],
            "dependency_map": dependency_map(ex),
            "dependency_status": dependencies,
            "dependency_status_by_id": dependency_status_by_id,
            "participant_briefs": list_participant_briefs(ex),
        },
    )


@app.post("/injects/{inject_id}/trigger")
async def trigger_inject(
    request: Request,
    inject_id: str,
):
    fields = await _form_fields(request)
    intensity = _field(fields, "intensity", "medium")
    duration_seconds = _integer_field(fields, "duration_seconds", 300)
    guardrail_profile = _field(fields, "guardrail_profile", "standard")
    pattern = _field(fields, "pattern", "steady")
    inj = get_inject(inject_id)
    if not inj:
        raise HTTPException(404, "Inject not found")
    ex = get_exercise(inj.exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    if inj.triggered and inj.action_type != "chaos_script":
        raise HTTPException(409, "Narrative inject has already been triggered")

    result = "Triggered narrative/artifact inject."
    if inj.action_type == "chaos_script":
        try:
            result = run_chaos_inject(
                ex,
                inj,
                intensity,
                duration_seconds,
                guardrail_profile,
                pattern,
            )
        except ValueError as exc:
            result = str(exc)
            add_event(ex.id, "inject_failed", inj.title, result)
            raise HTTPException(400, result) from exc
        except ChaosPreflightError as exc:
            result = str(exc)
            add_event(ex.id, "inject_preflight_failed", inj.title, result)
            raise HTTPException(503, result) from exc
        except ChaosExecutionError as exc:
            result = str(exc)
            add_event(ex.id, "inject_failed", inj.title, result)
            raise HTTPException(500, result) from exc
    elif inj.action_type == "artifact":
        try:
            result = artifact_trigger_result(ex, inj)
        except ValueError as exc:
            result = str(exc)
            add_event(ex.id, "inject_failed", inj.title, result)
            raise HTTPException(400, result) from exc

    mark_inject_triggered(inject_id)
    detail = f"Audience: {inj.audience}\nAction: {inj.action_type}"
    if inj.action_type == "chaos_script":
        detail += (
            f"\nIntensity: {intensity}"
            f"\nDuration: {duration_seconds} seconds"
            f"\nPattern: {pattern}"
            f"\nGuardrails: {guardrail_profile}"
        )
    add_event(ex.id, "inject_triggered", inj.title, f"{detail}\n{result}")
    return _redirect_to_exercise(ex)


@app.post("/exercises/{exercise_id}/chaos/reset")
async def reset_exercise_chaos(request: Request, exercise_id: str):
    action = _field(await _form_fields(request), "action", "")
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        result = reset_chaos(ex, action or None)
    except ChaosPreflightError as exc:
        add_event(ex.id, "chaos_reset_failed", "Chaos Reset Failed", str(exc))
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        add_event(ex.id, "chaos_reset_failed", "Chaos Reset Failed", str(exc))
        raise HTTPException(500, str(exc)) from exc

    label = action or "all actions"
    add_event(ex.id, "chaos_reset", "Chaos State Reset", f"Reset: {label}\n{result}")
    return _redirect_to_exercise(ex)


@app.post("/exercises/{exercise_id}/chaos/emergency-stop")
def emergency_stop_exercise_chaos(exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        result = emergency_stop(ex)
    except ChaosExecutionError as exc:
        add_event(
            ex.id,
            "chaos_emergency_stop_failed",
            "Emergency Stop Failed",
            str(exc),
        )
        raise HTTPException(503, str(exc)) from exc

    add_event(
        ex.id,
        "chaos_emergency_stop",
        "Emergency Stop",
        result,
    )
    return _redirect_to_exercise(ex)


@app.get("/exercises/{exercise_id}/chaos/status")
def exercise_chaos_status(exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    control_status = read_control_status(ex)
    dependencies = (
        read_dependency_status(ex)
        if control_status.get("matches_exercise")
        else {"reachable": False, "dependencies": []}
    )
    return JSONResponse(
        {
            "state": read_chaos_state(ex),
            "control": control_status,
            "dependencies": dependencies,
        }
    )


@app.post("/exercises/{exercise_id}/objectives/{objective_index}")
async def assess_exercise_objective(
    request: Request,
    exercise_id: str,
    objective_index: int,
):
    fields = await _form_fields(request)
    rating = _field(fields, "rating")
    notes = _field(fields, "notes", "")
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    if not 0 <= objective_index < len(ex.objectives):
        raise HTTPException(404, "Objective not found")
    if rating not in RATING_SCORES:
        raise HTTPException(400, "Unknown objective rating")
    notes = notes.strip()
    if len(notes) > 2000:
        raise HTTPException(400, "Objective notes must be 2000 characters or fewer")
    save_objective_assessment(
        exercise_id,
        objective_index,
        rating,
        notes,
    )
    add_event(
        exercise_id,
        "objective_assessed",
        f"Objective Assessed: {ex.objectives[objective_index]}",
        f"Rating: {RATING_LABELS[rating]}\nNotes: {notes or 'None'}",
    )
    return _redirect_to_exercise(ex)


@app.get("/exercises/{exercise_id}/reports/after-action.md")
def download_after_action_report(exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    _, events, chaos_state, intelligence = _exercise_evidence(ex)
    report = render_evidence_markdown(
        ex,
        intelligence,
        events,
        chaos_state,
    )
    report_path = exercise_package_path(
        ex,
        "reports",
        "after_action_report.md",
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
    return Response(
        report,
        media_type="text/markdown",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ex.id}-after-action.md"'
            )
        },
    )


@app.get("/exercises/{exercise_id}/reports/evidence.zip")
def download_evidence_package(exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    _, events, chaos_state, intelligence = _exercise_evidence(ex)
    archive = build_evidence_archive(
        ex,
        intelligence,
        events,
        chaos_state,
    )
    archive_path = exercise_package_path(
        ex,
        "reports",
        "evidence_package.zip",
    )
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_bytes(archive)
    return Response(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ex.id}-evidence.zip"'
            )
        },
    )


@app.post("/exercises/{exercise_id}/playbooks")
async def save_exercise_playbook(
    request: Request,
    exercise_id: str,
):
    playbook_yaml = _field(
        await _form_fields(request, maximum_bytes=96 * 1024),
        "playbook_yaml",
    )
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        playbook = save_playbook_configuration(ex, playbook_yaml)
    except ValueError as exc:
        add_event(ex.id, "playbook_save_failed", "Playbook Save Failed", str(exc))
        raise HTTPException(400, str(exc)) from exc
    except ChaosPreflightError as exc:
        add_event(ex.id, "playbook_save_failed", "Playbook Save Failed", str(exc))
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        add_event(ex.id, "playbook_save_failed", "Playbook Save Failed", str(exc))
        raise HTTPException(502, str(exc)) from exc
    add_event(
        ex.id,
        "playbook_saved",
        f"Playbook Saved: {playbook['name']}",
        f"ID: {playbook['id']}\nStages: {len(playbook['stages'])}",
    )
    return _redirect_to_exercise(ex)


@app.post("/exercises/{exercise_id}/playbooks/designer/validate")
def validate_designer_playbook(
    exercise_id: str,
    playbook: dict = Body(...),
):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        normalized = validate_playbook_configuration(ex, playbook)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ChaosPreflightError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        raise HTTPException(400, str(exc)) from exc
    return JSONResponse({"valid": True, "playbook": normalized})


@app.post("/exercises/{exercise_id}/playbooks/designer/save")
def save_designer_playbook(
    exercise_id: str,
    playbook: dict = Body(...),
):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        normalized = save_playbook_configuration(ex, playbook)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ChaosPreflightError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        raise HTTPException(400, str(exc)) from exc
    add_event(
        ex.id,
        "playbook_saved",
        f"Playbook Saved: {normalized['name']}",
        (
            f"ID: {normalized['id']}\n"
            f"Stages: {len(normalized['stages'])}\n"
            "Source: visual designer"
        ),
    )
    return JSONResponse({"saved": True, "playbook": normalized})


@app.post("/exercises/{exercise_id}/playbooks/{playbook_id}/clone")
async def clone_exercise_playbook(
    request: Request,
    exercise_id: str,
    playbook_id: str,
):
    fields = await _form_fields(request)
    new_playbook_id = _field(fields, "new_playbook_id")
    new_name = _field(fields, "new_name")
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        clone = clone_playbook_configuration(
            ex,
            playbook_id,
            new_playbook_id,
            new_name,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ChaosPreflightError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        raise HTTPException(400, str(exc)) from exc
    add_event(
        ex.id,
        "playbook_cloned",
        f"Playbook Cloned: {clone['name']}",
        f"Source: {playbook_id}\nClone: {clone['id']}",
    )
    return _redirect_to_exercise(ex)


@app.post("/exercises/{exercise_id}/playbooks/import")
async def import_exercise_playbook(
    request: Request,
    exercise_id: str,
):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    content_type = request.headers.get("content-type", "").split(";", 1)[0]
    if content_type not in {"application/yaml", "text/yaml", "text/plain"}:
        raise HTTPException(415, "Playbook import must use a YAML content type")
    filename = request.headers.get("x-livefire-filename", "imported-playbook.yml")
    if len(filename) > 120 or not filename.lower().endswith((".yml", ".yaml")):
        raise HTTPException(400, "Playbook filename must end in .yml or .yaml")
    content = await request.body()
    if len(content) > 64 * 1024:
        raise HTTPException(400, "Playbook configuration is too large")
    try:
        configuration = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(400, "Playbook must use UTF-8 encoding") from exc
    try:
        playbook = save_playbook_configuration(ex, configuration)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ChaosPreflightError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        raise HTTPException(400, str(exc)) from exc
    add_event(
        ex.id,
        "playbook_imported",
        f"Playbook Imported: {playbook['name']}",
        f"File: {filename}\nID: {playbook['id']}",
    )
    return _redirect_to_exercise(ex)


@app.get("/exercises/{exercise_id}/playbooks/{playbook_id}/export.yml")
def export_exercise_playbook(exercise_id: str, playbook_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        configuration = export_playbook_configuration(ex, playbook_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(
        configuration,
        media_type="application/yaml",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{playbook_id}.yml"'
            )
        },
    )


@app.post(
    "/exercises/{exercise_id}/playbooks/{playbook_id}"
    "/versions/{version_id}/restore"
)
def restore_exercise_playbook_version(
    exercise_id: str,
    playbook_id: str,
    version_id: str,
):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        playbook = restore_playbook_version(
            ex,
            playbook_id,
            version_id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ChaosPreflightError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        raise HTTPException(400, str(exc)) from exc
    add_event(
        ex.id,
        "playbook_restored",
        f"Playbook Restored: {playbook['name']}",
        f"Version: {version_id}",
    )
    return _redirect_to_exercise(ex)


@app.post("/exercises/{exercise_id}/playbooks/{playbook_id}/start")
def start_exercise_playbook(exercise_id: str, playbook_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        playbook_run = start_chaos_playbook(ex, playbook_id)
    except ChaosPreflightError as exc:
        add_event(ex.id, "playbook_start_failed", "Playbook Start Failed", str(exc))
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        add_event(ex.id, "playbook_start_failed", "Playbook Start Failed", str(exc))
        raise HTTPException(502, str(exc)) from exc
    add_event(
        ex.id,
        "playbook_started",
        f"Playbook Started: {playbook_run['name']}",
        f"Run: {playbook_run['id']}\nSeed: {playbook_run['seed']}",
    )
    return _redirect_to_exercise(ex)


@app.post(
    "/exercises/{exercise_id}/playbook-runs/{playbook_run_id}/{command}"
)
def control_exercise_playbook(
    exercise_id: str,
    playbook_run_id: str,
    command: str,
):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        result = control_chaos_playbook_run(
            ex,
            playbook_run_id,
            command,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ChaosPreflightError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        raise HTTPException(502, str(exc)) from exc
    add_event(
        ex.id,
        f"playbook_{command}",
        f"Playbook {command.title()}",
        f"Run: {result['id']}\nStatus: {result['status']}",
    )
    return _redirect_to_exercise(ex)


@app.post(
    "/exercises/{exercise_id}/playbook-runs/{playbook_run_id}"
    "/stages/{stage_id}/skip"
)
def skip_exercise_playbook_stage(
    exercise_id: str,
    playbook_run_id: str,
    stage_id: str,
):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        stage = skip_chaos_playbook_stage(
            ex,
            playbook_run_id,
            stage_id,
        )
    except ChaosPreflightError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ChaosExecutionError as exc:
        raise HTTPException(502, str(exc)) from exc
    add_event(
        ex.id,
        "playbook_stage_skipped",
        f"Playbook Stage Skipped: {stage['title']}",
        f"Run: {playbook_run_id}\nStage: {stage_id}",
    )
    return _redirect_to_exercise(ex)


@app.post("/exercises/{exercise_id}/artifacts")
async def create_exercise_artifact(
    request: Request,
    exercise_id: str,
):
    fields = await _form_fields(request)
    title = _field(fields, "title")
    audience = _field(fields, "audience")
    stage = _field(fields, "stage")
    artifact_kind = _field(fields, "artifact_kind")
    content = _field(fields, "content")
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    try:
        inject = create_safe_artifact_inject(
            ex,
            title,
            audience,
            stage,
            artifact_kind,
            content,
        )
    except PackagePathError:
        raise
    except OSError as exc:
        LOGGER.warning("Failed to write a safe exercise artifact")
        raise HTTPException(500, "Exercise artifact could not be written") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    save_injects([inject])
    add_event(
        ex.id,
        "artifact_created",
        f"Safe Artifact Created: {inject.title}",
        (
            f"Type: {artifact_kind}\n"
            f"Stage: {stage}\n"
            f"Path: {inject.payload['artifact']}"
        ),
    )
    return _redirect_to_exercise(ex)


@app.post("/exercises/{exercise_id}/events")
async def add_manual_event(request: Request, exercise_id: str):
    fields = await _form_fields(request)
    title = _field(fields, "title").strip()
    detail = _field(fields, "detail").strip()
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    if not title or len(title) > 120:
        raise HTTPException(400, "Event title must be between 1 and 120 characters")
    if not detail or len(detail) > 5000:
        raise HTTPException(400, "Event detail must be between 1 and 5000 characters")
    add_event(exercise_id, "manual_note", title, detail)
    return _redirect_to_exercise(ex)


@app.get("/exercises/{exercise_id}/download")
def download_exercise(exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    archive = build_exercise_archive(ex)
    return Response(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{ex.id}.zip"',
        },
    )
