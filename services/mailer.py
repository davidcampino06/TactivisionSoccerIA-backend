"""Outgoing e-mail (password recovery).

Pattern - Strategy: ``Mailer`` is the common interface and each provider is a concrete strategy.
The router only calls ``get_mailer().send(message)``; which provider runs is decided by the
``MAIL_PROVIDER`` environment variable, so a provider can be swapped without touching the
recovery logic.

    MAIL_PROVIDER=smtp   -> SmtpMailer   (any SMTP server, e.g. Gmail with an app password)
    MAIL_PROVIDER=brevo  -> BrevoMailer  (HTTP API; works where outbound SMTP ports are blocked)
    (unset)              -> no mailer: recovery cannot send e-mails

Secrets (SMTP password, API key) come only from environment variables and are never logged.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape

import httpx

from config import settings

logger = logging.getLogger("tactivision.mailer")

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


@dataclass(frozen=True)
class MailMessage:
    to: str
    to_name: str
    subject: str
    text: str
    html: str


class MailDeliveryError(Exception):
    """The provider rejected the message or could not be reached."""


class Mailer(ABC):
    @abstractmethod
    def send(self, message: MailMessage) -> None:
        """Delivers the message or raises MailDeliveryError."""


class SmtpMailer(Mailer):
    def send(self, message: MailMessage) -> None:
        email = EmailMessage()
        email["Subject"] = message.subject
        email["From"] = f"{settings.mail_from_name} <{settings.mail_from}>"
        email["To"] = message.to
        email.set_content(message.text)
        email.add_alternative(message.html, subtype="html")
        try:
            if settings.smtp_port == 465:
                with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15,
                                      context=ssl.create_default_context()) as server:
                    self._deliver(server, email)
            else:
                with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                    if settings.smtp_starttls:
                        server.starttls(context=ssl.create_default_context())
                    self._deliver(server, email)
        except (OSError, smtplib.SMTPException) as error:
            raise MailDeliveryError(f"SMTP delivery failed: {type(error).__name__}") from error

    @staticmethod
    def _deliver(server: smtplib.SMTP, email: EmailMessage) -> None:
        if settings.smtp_user:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(email)


class BrevoMailer(Mailer):
    def send(self, message: MailMessage) -> None:
        payload = {
            "sender": {"name": settings.mail_from_name, "email": settings.mail_from},
            "to": [{"email": message.to, "name": message.to_name}],
            "subject": message.subject,
            "textContent": message.text,
            "htmlContent": message.html,
        }
        try:
            response = httpx.post(BREVO_URL, json=payload, timeout=15,
                                  headers={"api-key": settings.brevo_api_key, "accept": "application/json"})
        except httpx.HTTPError as error:
            raise MailDeliveryError(f"Brevo unreachable: {type(error).__name__}") from error
        if response.status_code >= 300:
            raise MailDeliveryError(f"Brevo answered {response.status_code}")


_PROVIDERS: dict[str, type[Mailer]] = {"smtp": SmtpMailer, "brevo": BrevoMailer}


def get_mailer() -> Mailer | None:
    """The configured strategy, or None when no provider is set up."""
    provider = _PROVIDERS.get(settings.mail_provider)
    if provider is None or not settings.mail_from:
        return None
    return provider()


def recovery_link(token: str) -> str:
    # The token goes in the URL fragment (#): browsers never send it to a server or in the Referer.
    return f"{settings.frontend_url}/restablecer#token={token}"


def password_recovery_message(*, email: str, first_name: str, token: str) -> MailMessage:
    link = recovery_link(token)
    minutes = settings.password_reset_expire_minutes
    name = escape(first_name)
    text = (
        f"Hola {first_name},\n\n"
        "Recibimos una solicitud para restablecer la contraseña de tu cuenta de TactiVision IA.\n"
        f"Abre este enlace para crear una nueva (vence en {minutes} minutos y sirve una sola vez):\n\n"
        f"{link}\n\n"
        "Si no fuiste tú, ignora este correo: tu contraseña actual sigue funcionando.\n\n"
        "TactiVision IA"
    )
    html = f"""\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;color:#111714">
  <div style="background:#0b0f0e;color:#f3f4f0;padding:22px 26px;border-radius:12px 12px 0 0">
    <strong style="letter-spacing:.06em">TACTIVISION IA</strong>
  </div>
  <div style="border:1px solid #d6dbd8;border-top:0;padding:26px;border-radius:0 0 12px 12px">
    <p>Hola {name},</p>
    <p>Recibimos una solicitud para restablecer la contraseña de tu cuenta.</p>
    <p style="margin:26px 0">
      <a href="{escape(link, quote=True)}"
         style="background:#e3324a;color:#ffffff;padding:12px 20px;border-radius:999px;text-decoration:none;font-weight:bold">
        Crear nueva contraseña</a>
    </p>
    <p style="color:#606865;font-size:13px">El enlace vence en {minutes} minutos y sirve una sola vez.
      Si no fuiste tú, ignora este correo: tu contraseña actual sigue funcionando.</p>
  </div>
</div>"""
    return MailMessage(to=email, to_name=first_name, subject="Restablece tu contraseña de TactiVision IA",
                       text=text, html=html)


def send_quietly(mailer: Mailer, message: MailMessage) -> None:
    """Runs after the response (background task): a failure is logged, never shown to the requester."""
    try:
        mailer.send(message)
    except MailDeliveryError as error:
        logger.error("Password recovery e-mail not delivered: %s", error)
