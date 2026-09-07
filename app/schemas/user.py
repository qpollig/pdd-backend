import uuid
from datetime import datetime

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
    # Восстановление жизней: сейчас модель простая — ежесуточный сброс до lives_max в 00:00 UTC.
    lives_reset_at: datetime | None = None  # когда жизни сбрасывались в последний раз (null — ещё ни разу)
    lives_regen_at: datetime | None = None  # когда произойдёт следующий сброс (ближайшие 00:00 UTC)


class OAuthLoginRequest(BaseModel):
    code: str
    redirect_uri: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
