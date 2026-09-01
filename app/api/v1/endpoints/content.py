from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.content import TicketOut, TopicOut, TopicsListResponse
from app.services import content_repo

router = APIRouter(prefix="/topics", tags=["content"])


@router.get("", response_model=TopicsListResponse)
async def get_topics(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TopicsListResponse:
    topics = await content_repo.list_topics(db)
    tickets = await content_repo.list_tickets(db)
    return TopicsListResponse(
        topics=[TopicOut.model_validate(t) for t in topics],
        tickets=[TicketOut.model_validate(t) for t in tickets],
    )
