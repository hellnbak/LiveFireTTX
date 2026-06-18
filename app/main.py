# Copyright (c) 2026 Steve Manzuik
# Licensed under FSL-1.1-ALv2. See LICENSE.

from __future__ import annotations

from pathlib import Path
import subprocess

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
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
from app.version import __version__

BASE = Path(__file__).resolve().parent
app = FastAPI(title="LiveFireTTX", version=__version__)
templates = Jinja2Templates(directory=str(BASE / "templates"))
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
    req = ExerciseCreate(
        name=name,
        scenario_type=scenario_type,
        platform=platform,
        business_system=business_system,
        difficulty=difficulty,
        duration_minutes=duration_minutes,
        participants=[p.strip() for p in participants.split(",") if p.strip()],
        objectives=[o.strip() for o in objectives.split("\n") if o.strip()],
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
    return templates.TemplateResponse("exercise.html", {"request": request, "exercise": ex, "injects_by_stage": by_stage, "events": events})


@app.post("/injects/{inject_id}/trigger")
def trigger_inject(inject_id: str):
    inj = get_inject(inject_id)
    if not inj:
        raise HTTPException(404, "Inject not found")
    ex = get_exercise(inj.exercise_id)
    if not ex:
        raise HTTPException(404, "Exercise not found")

    result = "Triggered narrative/artifact inject."
    if inj.action_type == "chaos_script" and inj.script_name:
        script = Path(ex.package_path) / "chaos" / inj.script_name
        if not script.exists():
            raise HTTPException(404, f"Chaos script not found: {inj.script_name}")
        proc = subprocess.run(["python3", str(script)], cwd=str(script.parent), capture_output=True, text=True, timeout=15)
        result = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            add_event(ex.id, "inject_failed", inj.title, result)
            raise HTTPException(500, result)

    mark_inject_triggered(inject_id)
    add_event(ex.id, "inject_triggered", inj.title, f"Audience: {inj.audience}\nAction: {inj.action_type}\n{result}")
    return RedirectResponse(f"/exercises/{inj.exercise_id}", status_code=303)


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
