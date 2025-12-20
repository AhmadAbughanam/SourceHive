from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import parseaddr


def _read_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def is_valid_email(value: str) -> bool:
    raw = (value or "").strip()
    if not raw or "@" not in raw:
        return False
    _, addr = parseaddr(raw)
    if not addr or "@" not in addr:
        return False
    local, domain = addr.rsplit("@", 1)
    return bool(local) and "." in domain


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    use_tls: bool
    user: str
    password: str
    mail_from: str

    @staticmethod
    def from_env() -> "SmtpConfig":
        host = _read_env("SMTP_HOST", "")
        user = _read_env("SMTP_USER", "")
        password = _read_env("SMTP_PASSWORD", "")
        mail_from = _read_env("SMTP_FROM", user or "")
        port = int(_read_env("SMTP_PORT", "587") or 587)
        use_tls = (_read_env("SMTP_USE_TLS", "1") or "1").strip() not in ("0", "false", "False", "no", "NO")

        if not host or not user or not password or not mail_from:
            raise ValueError("SMTP configuration is incomplete. Set SMTP_HOST/SMTP_USER/SMTP_PASSWORD/SMTP_FROM.")

        return SmtpConfig(host=host, port=port, use_tls=use_tls, user=user, password=password, mail_from=mail_from)


def send_email(*, to_email: str, subject: str, body: str, config: SmtpConfig) -> None:
    if not is_valid_email(to_email):
        raise ValueError("Destination email is invalid")

    msg = EmailMessage()
    msg["From"] = config.mail_from
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP(config.host, config.port, timeout=20) as smtp:
        smtp.ehlo()
        if config.use_tls:
            smtp.starttls(context=context)
            smtp.ehlo()
        smtp.login(config.user, config.password)
        smtp.send_message(msg)

