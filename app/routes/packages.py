from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.models import get_exercise
from app.services.packages import participant_brief_content
from app.services.paths import PackagePathError


router = APIRouter(prefix="/exercises", tags=["packages"])


@router.get(
    "/{exercise_id}/participants/{filename}",
    response_class=Response,
)
def download_participant_brief(exercise_id: str, filename: str):
    exercise = get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(404, "Exercise not found")
    try:
        content = participant_brief_content(exercise, filename)
    except (OSError, PackagePathError, ValueError) as exc:
        raise HTTPException(404, "Participant brief is unavailable") from exc
    return Response(
        content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
