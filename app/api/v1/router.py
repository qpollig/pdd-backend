from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    billing,
    content,
    progress,
    questions,
    sessions,
    subscriptions,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(content.router)
api_router.include_router(questions.router)
api_router.include_router(sessions.router)
api_router.include_router(progress.router)
api_router.include_router(billing.router)
api_router.include_router(subscriptions.router)
