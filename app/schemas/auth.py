from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.auth_identity import AuthIdentityType

# Пароль: минимум 8 (по ТЗ задачи), максимум 72 — предел bcrypt (байты сверх 72-го
# игнорируются, тихая обрезка = дыра в безопасности, поэтому режем на входе).
_PASSWORD = Field(min_length=8, max_length=72)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = _PASSWORD
    name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)  # тут длину не валидируем строго — просто отвергаем


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    new_password: str = _PASSWORD


class MessageResponse(BaseModel):
    """Нейтральный ответ там, где по соображениям безопасности нельзя раскрывать результат
    (forgot/reset). detail — человекочитаемый текст, не код ошибки."""

    detail: str


# ── Связывание способов входа (Фаза 1, продолжение) ──────────────────────────────────────────
class LinkPasswordRequest(BaseModel):
    """Добавить вход по паролю аккаунту, заведённому через OAuth."""

    email: EmailStr
    password: str = _PASSWORD


class IdentityOut(BaseModel):
    """Один привязанный способ входа. Ответ не публичный (только владельцу по Bearer),
    поэтому identifier (email / oauth_id) отдаётся как есть, без маскирования."""

    model_config = ConfigDict(from_attributes=True)

    type: AuthIdentityType
    identifier: str
    created_at: datetime
