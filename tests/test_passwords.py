"""Юнит-тесты app/services/passwords.py."""

from app.services.passwords import hash_password, verify_password


def test_hash_is_not_plaintext_and_is_bcrypt():
    h = hash_password("correct horse battery staple")
    assert h != "correct horse battery staple"
    assert h.startswith("$2b$")  # bcrypt-хеш
    assert len(h) == 60


def test_hash_is_salted_unique_per_call():
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_roundtrip():
    h = hash_password("my-password-123")
    assert verify_password("my-password-123", h) is True
    assert verify_password("my-password-124", h) is False


def test_verify_none_hash_is_false():
    # identity без пароля (oauth) -> verify всегда False, но без исключения (dummy_verify)
    assert verify_password("anything", None) is False
    assert verify_password("anything", "") is False


def test_bcrypt_72_byte_truncation_is_handled():
    """bcrypt смотрит только на первые 72 байта. Схема ограничивает пароль 72 символами,
    здесь фиксируем, что _truncate() приводит длинные строки к согласованному виду:
    пароли, различающиеся только после 72-го байта, считаются одинаковыми."""
    base = "A" * 72
    h = hash_password(base + "-tail-one")
    assert verify_password(base + "-tail-two", h) is True
