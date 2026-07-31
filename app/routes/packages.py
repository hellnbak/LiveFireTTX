from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.models import get_exercise
from app.services.packages import participant_brief_path


router = APIRouter(prefix="/exercises", tags=["packages"])


@router.get(
    "/{exercise_id}/participants/{filename}",
    response_class=FileResponse,
)
def download_participant_brief(exercise_id: str, filename: str):
    exercise = get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(404, "Exercise not found")
    try:
        path = participant_brief_path(exercise, filename)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(
        path,
        filename=filename,
        media_type="text/markdown",
    )
