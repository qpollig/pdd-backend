from pydantic import BaseModel, EmailStr, Field

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
