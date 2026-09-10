"""Хеширование и проверка паролей.

passlib CryptContext поверх bcrypt. Выбор bcrypt обоснован в requirements.txt. CryptContext
даёт:
  * таймсейф-сравнение внутри verify() (constant-time на уровне bcrypt);
  * verify_and_update() — прозрачный rehash, если параметры/схема устарели;
  * agility — во Фазе 2 можно добавить argon2 первой схемой, не трогая вызовы.

bcrypt игнорирует байты пароля после 72-го — поэтому на уровне схемы (app/schemas/auth.py)
пароль ограничен 72 символами, здесь дополнительно обрезаем по 72 байтам как защита в глубину.
"""

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_BCRYPT_MAX_BYTES = 72


def _truncate(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) <= _BCRYPT_MAX_BYTES:
        return password
    # Обрезаем по границе валидного UTF-8, чтобы не расколоть многобайтовый символ.
    return encoded[:_BCRYPT_MAX_BYTES].decode("utf-8", errors="ignore")


def hash_password(password: str) -> str:
    return _pwd_context.hash(_truncate(password))


def verify_password(password: str, password_hash: str | None) -> bool:
    """Таймсейф-проверка. `password_hash=None` (identity без пароля) -> всегда False,
    но всё равно прогоняем фиктивный verify, чтобы время ответа не выдавало отсутствие хеша."""
    if not password_hash:
        _pwd_context.dummy_verify()
        return False
    return _pwd_context.verify(_truncate(password), password_hash)
