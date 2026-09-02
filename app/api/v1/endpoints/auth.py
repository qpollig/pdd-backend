from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user import OAuthProvider
from app.schemas.common import ErrorDetail
from app.schemas.user import OAuthLoginRequest, TokenResponse
from app.services import user_repo
from app.services.oauth import OAuthError, exchange_code_and_fetch_profile

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/oauth/{provider}",
    response_model=TokenResponse,
    responses={
        400: {
            "model": ErrorDetail,
            "description": "OAUTH_EXCHANGE_FAILED — провайдер отклонил code (истёк/уже использован/неверный "
            "redirect_uri); UNSUPPORTED_PROVIDER — недостижимо при валидном provider из пути",
        },
    },
)
async def oauth_login(
    provider: OAuthProvider,
    payload: OAuthLoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    redirect_uri = payload.redirect_uri or settings.OAUTH_REDIRECT_URI

    try:
        profile = await exchange_code_and_fetch_profile(provider, payload.code, redirect_uri)
    except OAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAUTH_EXCHANGE_FAILED") from exc

    user = await user_repo.create_or_update_oauth_user(
        db,
        provider=provider,
        oauth_id=profile.oauth_id,
        name=profile.name,
        email=profile.email,
        avatar_url=profile.avatar_url,
    )

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=await user_repo.build_user_out(db, user))
