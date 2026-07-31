# Copyright (c) 2026 Steve Manzuik
# Licensed under FSL-1.1-ALv2. See LICENSE.

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.models import (
    ExerciseCreate,
    SCENARIO_LIBRARY,
    add_event,
    get_exercise,
    get_inject,
    get_injects,
    init_db,
    list_events,
    list_exercises,
    mark_inject_triggered,
    save_exercise,
    save_injects,
)
from app.services.generator import create_exercise_from_request
from app.services.runtime import (
    ChaosExecutionError,
    ChaosPreflightError,
    control_chaos_playbook_run,
    emergency_stop,
    read_chaos_state,
    read_control_status,
    read_playbook_configuration,
    reset_chaos,
    run_chaos_inject,
    save_playbook_configuration,
    skip_chaos_playbook_stage,
    start_chaos_playbook,
)
from app.version import __version__

BASE = Path(__file__).resolve().parent
app = FastAPI(title="LiveFireTTX", version=__version__)
templates = Jinja2Templates(directory=str(BASE / "templates"))
templates.env.globals["app_version"] = __version__
app.mount("/static", StaticFiles(directory=str(BASE / "templates" / "static")), name="static")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "exercises": list_exercises(), "scenarios": SCENARIO_LIBRARY})


@app.get("/new", response_class=HTMLResponse)
def new_exercise(request: Request):
    return templates.TemplateResponse("new.html", {"request": request, "scenarios": SCENARIO_LIBRARY})


@app.post("/exercises")
def create_exercise(
    name: str = Form(...),
    scenario_type: str = Form(...),
    platform: str = Form("local_docker"),
    business_system: str = Form("Order Processing"),
    difficulty: str = Form("intermediate"),
    duration_minutes: int = Form(90),
    participants: str = Form("Incident Commander, Security Operations, Cloud/IT Operations, Communications, Business Owner"),
    objectives: str = Form(""),
):
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
    add_event(ex.id, "exercise_created", "Exercise Created", f"Generated package at {ex.package_path}")
    return RedirectResponse(f"/exercises/{ex.id}", status_code=303)


@app.get("/exercises/{exercise_id}", response_class=HTMLResponse)
def exercise_detail(request: Request, exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    injects = get_injects(exercise_id)
    events = list_events(exercise_id)
    by_stage = {}
    for i in injects:
        by_stage.setdefault(i.stage, []).append(i)
    return templates.TemplateResponse(
        "exercise.html",
        {
            "request": request,
            "exercise": ex,
            "injects_by_stage": by_stage,
            "events": events,
            "chaos_state": read_chaos_state(ex),
            "control_status": read_control_status(ex),
            "playbook_configuration": read_playbook_configuration(ex),
        },
    )


@app.post("/injects/{inject_id}/trigger")
def trigger_inject(
    inject_id: str,
    intensity: str = Form("medium"),
    duration_seconds: int = Form(300),
    guardrail_profile: str = Form("standard"),
    pattern: str = Form("steady"),
):
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
    return RedirectResponse(f"/exercises/{inj.exercise_id}", status_code=303)


@app.post("/exercises/{exercise_id}/chaos/reset")
def reset_exercise_chaos(exercise_id: str, action: str = Form("")):
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
    return RedirectResponse(f"/exercises/{exercise_id}", status_code=303)


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
    return RedirectResponse(f"/exercises/{exercise_id}", status_code=303)


@app.get("/exercises/{exercise_id}/chaos/status")
def exercise_chaos_status(exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    return JSONResponse(
        {
            "state": read_chaos_state(ex),
            "control": read_control_status(ex),
        }
    )


@app.post("/exercises/{exercise_id}/playbooks")
def save_exercise_playbook(
    exercise_id: str,
    playbook_yaml: str = Form(...),
):
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
    return RedirectResponse(f"/exercises/{exercise_id}", status_code=303)


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
    return RedirectResponse(f"/exercises/{exercise_id}", status_code=303)


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
    return RedirectResponse(f"/exercises/{exercise_id}", status_code=303)


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
    return RedirectResponse(f"/exercises/{exercise_id}", status_code=303)


@app.post("/exercises/{exercise_id}/events")
def add_manual_event(exercise_id: str, title: str = Form(...), detail: str = Form(...)):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    add_event(exercise_id, "manual_note", title, detail)
    return RedirectResponse(f"/exercises/{exercise_id}", status_code=303)


@app.get("/exercises/{exercise_id}/download")
def download_exercise(exercise_id: str):
    ex = get_exercise(exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")
    import shutil
    archive = shutil.make_archive(str(Path(ex.package_path)), "zip", root_dir=ex.package_path)
    return FileResponse(archive, filename=f"{exercise_id}.zip", media_type="application/zip")
