from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, get_current_user
from app.models.auth_identity import AuthIdentityType
from app.models.user import OAuthProvider, User
from app.schemas.auth import (
    ForgotPasswordRequest,
    IdentityOut,
    LinkPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
)
from app.schemas.common import ErrorDetail
from app.schemas.user import OAuthLoginRequest, TokenResponse
from app.services import auth_identity_repo, rate_limit, user_repo
from app.services.email import EmailMessage, get_email_sender
from app.services.oauth import OAuthError, exchange_code_and_fetch_profile
from app.services.passwords import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


# ─────────────────────────────────────────────────────────────────────────────────────────────
# OAuth (Yandex/VK) — контракт не изменился. Внутри теперь создаётся auth_identities вместо
# прямых колонок в users (см. app/services/user_repo.create_or_update_oauth_user).
# ─────────────────────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Email + пароль — второй способ входа, параллельно с OAuth.
#
# РЕШЕНИЕ (сверить отдельно): верификация email в Фазе 1 — ОПЦИОНАЛЬНАЯ. /register сразу
# возвращает рабочий токен (auto-login), email_verified_at остаётся NULL. Обоснование:
#   * на dev-сервере SMTP не настроен (письма только в лог) — обязательный gate сделал бы
#     register→login нерабочим без ручного чтения логов;
#   * OAuth-пользователи и так входят сразу (провайдер уже подтвердил почту) — держать
#     password-пользователей за лишним барьером при заглушечном SMTP непоследовательно для MVP;
#   * полноценный verify-флоу (endpoint + обязательность) — естественная часть Фазы 2 вместе
#     с несколькими способами входа и реальным SMTP-провайдером.
# Колонка email_verified_at и вся обвязка писем уже на месте — Фазе 2 останется добавить
# POST /auth/email/verify и сделать проверку обязательной.
# ─────────────────────────────────────────────────────────────────────────────────────────────
@router.post(
    "/register",
    response_model=TokenResponse,
    responses={409: {"model": ErrorDetail, "description": "EMAIL_ALREADY_REGISTERED — этот email уже зарегистрирован"}},
)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    email = auth_identity_repo.normalize_email(payload.email)

    existing = await auth_identity_repo.get_password_identity_by_email(db, email)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="EMAIL_ALREADY_REGISTERED")

    user, _identity = await user_repo.create_password_user(
        db, email=email, name=payload.name, password_hash=hash_password(payload.password)
    )

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=await user_repo.build_user_out(db, user))


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        401: {"model": ErrorDetail, "description": "INVALID_CREDENTIALS — неверный email или пароль (не уточняем, что именно)"},
        429: {"model": ErrorDetail, "description": "RATE_LIMITED — превышен лимит попыток входа для этого email+IP"},
    },
)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    email = auth_identity_repo.normalize_email(payload.email)
    rate_limit.enforce(
        "login",
        f"{email}|{rate_limit.client_ip(request)}",
        max_hits=settings.LOGIN_RATE_MAX_ATTEMPTS,
        window_seconds=settings.LOGIN_RATE_WINDOW_MINUTES * 60,
    )

    identity = await auth_identity_repo.get_password_identity_by_email(db, email)
    # verify_password таймсейф и при identity=None (dummy_verify) — время ответа не выдаёт,
    # существует ли email. Единый 401 в обоих случаях.
    if not verify_password(payload.password, identity.password_hash if identity else None):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_CREDENTIALS")

    user = await user_repo.get_user_by_id(db, identity.user_id)
    if user is None:  # рассинхрон FK — практически недостижимо
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="INVALID_CREDENTIALS")

    token = create_access_token(user.id)
    return TokenResponse(access_token=token, user=await user_repo.build_user_out(db, user))


@router.post("/password/forgot", response_model=MessageResponse)
async def forgot_password(
    payload: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> MessageResponse:
    """Всегда 200 с одинаковым телом — существование email по ответу определить нельзя.
    Отдельный rate limit: по email (защита чужого ящика от бомбардировки) и по IP."""
    email = auth_identity_repo.normalize_email(payload.email)
    window = settings.PASSWORD_FORGOT_RATE_WINDOW_MINUTES * 60
    rate_limit.enforce(
        "pw_forgot_email", email, max_hits=settings.PASSWORD_FORGOT_RATE_MAX_PER_EMAIL, window_seconds=window
    )
    rate_limit.enforce(
        "pw_forgot_ip",
        rate_limit.client_ip(request),
        max_hits=settings.PASSWORD_FORGOT_RATE_MAX_PER_IP,
        window_seconds=window,
    )

    identity = await auth_identity_repo.get_password_identity_by_email(db, email)
    if identity is not None:
        raw_token = await auth_identity_repo.create_password_reset_token(db, identity)
        reset_link = f"{settings.FRONTEND_PASSWORD_RESET_URL}?token={raw_token}"
        await get_email_sender().send(
            EmailMessage(
                to=email,
                subject="Сброс пароля — PDD Test Platform",
                body_text=(
                    "Вы (или кто-то другой) запросили сброс пароля.\n\n"
                    f"Ссылка (действует {settings.PASSWORD_RESET_TOKEN_TTL_MINUTES} минут):\n"
                    f"{reset_link}\n\n"
                    "Если это были не вы — просто проигнорируйте письмо, пароль не изменится."
                ),
            )
        )

    return MessageResponse(
        detail="Если такой email зарегистрирован, на него отправлено письмо со ссылкой для сброса пароля."
    )


@router.post(
    "/password/reset",
    response_model=MessageResponse,
    responses={400: {"model": ErrorDetail, "description": "INVALID_OR_EXPIRED_TOKEN — токен неизвестен, истёк или уже использован"}},
)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)) -> MessageResponse:
    identity = await auth_identity_repo.consume_password_reset_token(db, payload.token)
    if identity is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="INVALID_OR_EXPIRED_TOKEN")

    identity.password_hash = hash_password(payload.new_password)
    await db.flush()
    return MessageResponse(detail="Пароль изменён. Войдите с новым паролем.")


# ─────────────────────────────────────────────────────────────────────────────────────────────
# Связывание способов входа с аккаунтом (Фаза 1, продолжение).
#
# ВСЕ ручки ниже требуют валидный Bearer-токен: связывание — это ЯВНОЕ действие уже
# залогиненного пользователя. Автосвязывания по совпадению email НЕТ и быть не должно —
# email у password-пользователей в Фазе 1 не верифицирован, и авто-merge по email позволил бы
# угнать чужой Yandex/VK-аккаунт, зарегистрировав на его адрес пароль.
#
# Вход через /auth/oauth/{provider} (без токена) не меняется: неизвестный oauth_id по-прежнему
# создаёт нового пользователя. «Добавить ещё один способ входа к существующему аккаунту» — это
# отдельный UI-шаг «Привязать» в залогиненном состоянии, который бьёт СЮДА.
# ─────────────────────────────────────────────────────────────────────────────────────────────
async def _identities_out(db: AsyncSession, user: User) -> list[IdentityOut]:
    rows = await auth_identity_repo.list_identities_for_user(db, user.id)
    return [IdentityOut.model_validate(row) for row in rows]


@router.get("/identities", response_model=list[IdentityOut])
async def list_identities(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[IdentityOut]:
    """Способы входа текущего пользователя."""
    return await _identities_out(db, user)


@router.post(
    "/identities/oauth/{provider}",
    response_model=list[IdentityOut],
    responses={
        400: {"model": ErrorDetail, "description": "OAUTH_EXCHANGE_FAILED — провайдер отклонил code"},
        409: {
            "model": ErrorDetail,
            "description": "IDENTITY_ALREADY_LINKED — этот аккаунт провайдера уже привязан к ДРУГОМУ пользователю",
        },
    },
)
async def link_oauth_identity(
    provider: OAuthProvider,
    payload: OAuthLoginRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[IdentityOut]:
    """Привязать Yandex/VK-вход к текущему аккаунту. Тело — как у /auth/oauth/{provider}."""
    redirect_uri = payload.redirect_uri or settings.OAUTH_REDIRECT_URI
    try:
        profile = await exchange_code_and_fetch_profile(provider, payload.code, redirect_uri)
    except OAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAUTH_EXCHANGE_FAILED") from exc

    identity_type = AuthIdentityType(provider.value)
    existing = await auth_identity_repo.get_identity(db, identity_type, profile.oauth_id)
    if existing is not None:
        if existing.user_id == user.id:
            return await _identities_out(db, user)  # уже привязано к нам — идемпотентно
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="IDENTITY_ALREADY_LINKED")

    await auth_identity_repo.create_oauth_identity(db, user.id, identity_type, profile.oauth_id)
    return await _identities_out(db, user)


@router.post(
    "/identities/password",
    response_model=list[IdentityOut],
    responses={
        409: {
            "model": ErrorDetail,
            "description": "PASSWORD_ALREADY_SET — у пользователя уже есть вход по паролю (нужна отдельная "
            "смена пароля); EMAIL_ALREADY_REGISTERED — email занят другим пользователем",
        },
    },
)
async def link_password_identity(
    payload: LinkPasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[IdentityOut]:
    """Добавить вход по паролю аккаунту, заведённому через OAuth."""
    # Своё состояние проверяем первым: если пароль уже есть — это не «добавить», а «сменить»
    # (отдельная задача), поэтому 409 даже если email в теле — тот же самый.
    if await auth_identity_repo.password_identity_for_user(db, user.id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PASSWORD_ALREADY_SET")

    email = auth_identity_repo.normalize_email(payload.email)
    if await auth_identity_repo.get_password_identity_by_email(db, email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="EMAIL_ALREADY_REGISTERED")

    await auth_identity_repo.create_password_identity(db, user.id, email, hash_password(payload.password))
    return await _identities_out(db, user)


@router.delete(
    "/identities/{identity_type}",
    response_model=list[IdentityOut],
    responses={
        404: {"model": ErrorDetail, "description": "IDENTITY_NOT_FOUND — у пользователя нет способа входа этого типа"},
        409: {
            "model": ErrorDetail,
            "description": "CANNOT_UNLINK_LAST_IDENTITY — нельзя убрать последний способ входа (аккаунт станет недоступен)",
        },
    },
)
async def unlink_identity(
    identity_type: AuthIdentityType,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[IdentityOut]:
    """Отвязать способ входа. Последний оставшийся отвязать нельзя."""
    identities = await auth_identity_repo.list_identities_for_user(db, user.id)
    to_remove = [i for i in identities if i.type == identity_type]
    if not to_remove:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IDENTITY_NOT_FOUND")
    if len(to_remove) >= len(identities):  # после удаления не осталось бы ни одного
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="CANNOT_UNLINK_LAST_IDENTITY"
        )

    for identity in to_remove:
        await db.delete(identity)
    await db.flush()
    return await _identities_out(db, user)
