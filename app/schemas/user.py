import uuid

from pydantic import BaseModel, ConfigDict

from app.models.user import OAuthProvider


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    oauth_provider: OAuthProvider
    name: str | None
    avatar_url: str | None
    email: str | None
    lives_current: int
    lives_max: int
    is_premium: bool
    errors_count: int = 0  # сколько вопросов сейчас в "Работе над ошибками" (user_errors)
    favorites_count: int = 0  # сколько вопросов в "Избранном" (user_favorites)


class OAuthLoginRequest(BaseModel):
    code: str
    redirect_uri: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
