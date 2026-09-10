"""Отправка писем: интерфейс + SMTP-реализация + консольная заглушка.

Заглушка включается, когда SMTP_HOST пуст (тот же паттерн, что OAUTH_ALLOW_MOCK и
mock-эквайринг — не плодим новый стиль): письмо не уходит по сети, а печатается в лог
backend'а. Для продакшена нужен реальный SMTP-провайдер с настроенными SPF/DKIM,
иначе письма попадут в спам (см. README).
"""

import logging
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from typing import Protocol

import aiosmtplib

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    to: str
    subject: str
    body_text: str


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailSender:
    """Dev/дев-сервер без SMTP: печатаем письмо в лог, ничего не отправляя."""

    async def send(self, message: EmailMessage) -> None:
        logger.info(
            "[email:console] SMTP не настроен — письмо НЕ отправлено, вывожу в лог:\n"
            "  To: %s\n  From: %s\n  Subject: %s\n  ---\n%s\n  ---",
            message.to,
            settings.SMTP_FROM,
            message.subject,
            message.body_text,
        )


class SmtpEmailSender:
    async def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = settings.SMTP_FROM
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.body_text)

        await aiosmtplib.send(
            mime,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            start_tls=settings.SMTP_STARTTLS,
        )
        logger.info("[email:smtp] отправлено на %s (subject=%r)", message.to, message.subject)


def get_email_sender() -> EmailSender:
    return SmtpEmailSender() if settings.SMTP_HOST else ConsoleEmailSender()
