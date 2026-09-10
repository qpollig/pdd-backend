"""app/services/email.py — по задаче покрываем только заглушку:
без SMTP_HOST письмо не уходит по сети, а пишется в лог. Полноценный SMTP не поднимаем."""

import logging

import pytest

from app.services.email import ConsoleEmailSender, EmailMessage, SmtpEmailSender, get_email_sender


def test_get_email_sender_is_console_when_smtp_host_empty():
    # conftest выставляет SMTP_HOST="" -> заглушка
    assert isinstance(get_email_sender(), ConsoleEmailSender)


def test_get_email_sender_is_smtp_when_host_configured(monkeypatch):
    monkeypatch.setattr("app.services.email.settings.SMTP_HOST", "smtp.example.com")
    assert isinstance(get_email_sender(), SmtpEmailSender)


async def test_console_sender_logs_message_and_sends_nothing(caplog):
    caplog.set_level(logging.INFO, logger="app.services.email")
    await ConsoleEmailSender().send(
        EmailMessage(to="user@example.com", subject="Тема", body_text="ссылка: https://x/reset?token=abc")
    )
    record = "\n".join(r.message for r in caplog.records)
    assert "user@example.com" in record
    assert "reset?token=abc" in record
    assert "SMTP не настроен" in record
