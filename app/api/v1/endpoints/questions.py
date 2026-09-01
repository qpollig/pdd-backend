import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services import content_repo

router = APIRouter(prefix="/questions", tags=["content"])


@router.get("/{question_id}/image")
async def get_question_image(
    question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    question = await content_repo.get_question(db, question_id)
    if question is None or not question.image_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IMAGE_NOT_FOUND")

    return Response(
        content=question.image_data,
        media_type=question.image_content_type or "application/octet-stream",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
