import mimetypes
import os
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from pathlib import Path
from typing import Iterable, Sequence


class SMTPAuthenticationFailedError(RuntimeError):
    """Raised when the SMTP server rejects configured credentials."""


class SMTPSenderRejectedError(RuntimeError):
    """Raised when the SMTP server does not authorize the From address."""


def _read_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be one of true/false, yes/no, on/off, or 1/0.")


def _read_positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc

    if value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def parse_recipients(values: Iterable[str] | None) -> list[str]:
    recipients: list[str] = []
    seen = set()

    for value in values or []:
        for item in str(value).split(","):
            recipient = item.strip()
            if not recipient:
                continue

            display_name, address = parseaddr(recipient)
            if not address or "@" not in address or "\r" in recipient or "\n" in recipient:
                raise ValueError(f"Invalid email recipient: {recipient!r}")

            normalized = address.lower()
            if normalized in seen:
                continue

            seen.add(normalized)
            recipients.append(f"{display_name} <{address}>" if display_name else address)

    return recipients


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    sender: str
    username: str = ""
    password: str = field(default="", repr=False)
    use_tls: bool = True
    use_ssl: bool = False
    timeout: int = 30

    @classmethod
    def from_env(cls) -> "SMTPConfig":
        use_ssl = _read_bool("SMTP_USE_SSL", False)
        use_tls = _read_bool("SMTP_USE_TLS", not use_ssl)
        config = cls(
            host=os.getenv("SMTP_HOST", "").strip(),
            port=_read_positive_int(
                "SMTP_PORT",
                465 if use_ssl else 587,
            ),
            sender=os.getenv("SMTP_FROM", "").strip(),
            username=os.getenv("SMTP_USERNAME", "").strip(),
            password=os.getenv("SMTP_PASSWORD", ""),
            use_tls=use_tls,
            use_ssl=use_ssl,
            timeout=_read_positive_int("SMTP_TIMEOUT", 30),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not self.host:
            raise ValueError("SMTP_HOST is required when sending email.")
        if not self.sender:
            raise ValueError("SMTP_FROM is required when sending email.")
        if self.use_tls and self.use_ssl:
            raise ValueError("SMTP_USE_TLS and SMTP_USE_SSL cannot both be enabled.")
        if self.username and not self.password:
            raise ValueError("SMTP_PASSWORD is required when SMTP_USERNAME is set.")
        if self.password and not self.username:
            raise ValueError("SMTP_USERNAME is required when SMTP_PASSWORD is set.")

        _, sender_address = parseaddr(self.sender)
        if (
            not sender_address
            or "@" not in sender_address
            or "\r" in self.sender
            or "\n" in self.sender
        ):
            raise ValueError("SMTP_FROM must be a valid email address.")


class SMTPMailer:
    def __init__(self, config: SMTPConfig):
        config.validate()
        self.config = config

    def send(
        self,
        subject: str,
        body: str,
        recipients: Sequence[str],
        attachments: Sequence[str | Path] = (),
        html_body: str | None = None,
    ) -> str:
        normalized_recipients = parse_recipients(recipients)
        if not normalized_recipients:
            raise ValueError("At least one email recipient is required.")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.config.sender
        message["To"] = ", ".join(normalized_recipients)
        message["Date"] = formatdate(localtime=True)
        message["Message-ID"] = make_msgid()
        message.set_content(body)
        if html_body is not None:
            message.add_alternative(html_body, subtype="html")

        for attachment in attachments:
            self._attach_file(message, Path(attachment))

        context = ssl.create_default_context()
        if self.config.use_ssl:
            smtp_client = smtplib.SMTP_SSL(
                self.config.host,
                self.config.port,
                timeout=self.config.timeout,
                context=context,
            )
        else:
            smtp_client = smtplib.SMTP(
                self.config.host,
                self.config.port,
                timeout=self.config.timeout,
            )

        with smtp_client as client:
            if self.config.use_tls:
                client.starttls(context=context)
            if self.config.username:
                try:
                    client.login(
                        self.config.username,
                        self.config.password,
                    )
                except smtplib.SMTPAuthenticationError as exc:
                    provider_hint = ""
                    if self.config.host.lower() == "smtp.naver.com":
                        provider_hint = (
                            " For NAVER Mail, enable POP3/SMTP, enable "
                            "two-step verification, and use an application "
                            "password instead of the normal login password."
                        )
                    elif self.config.host.lower() == "smtp.worksmobile.com":
                        provider_hint = (
                            " For NAVER WORKS, use the full WORKS email "
                            "address as SMTP_USERNAME and use a third-party "
                            "app password instead of the normal account "
                            "password. The administrator must also allow "
                            "POP3/IMAP access."
                        )
                    raise SMTPAuthenticationFailedError(
                        "SMTP authentication failed"
                        f" (status={exc.smtp_code}). Check SMTP_USERNAME and "
                        f"SMTP_PASSWORD.{provider_hint}"
                    ) from None
            try:
                client.send_message(
                    message,
                    from_addr=parseaddr(self.config.sender)[1],
                    to_addrs=[parseaddr(recipient)[1] for recipient in normalized_recipients],
                )
            except smtplib.SMTPSenderRefused as exc:
                provider_hint = ""
                if self.config.host.lower() == "smtp.worksmobile.com":
                    provider_hint = (
                        " For NAVER WORKS, set SMTP_FROM to the full email "
                        "address used by SMTP_USERNAME, or to an alias that "
                        "the WORKS administrator has explicitly authorized."
                    )
                raise SMTPSenderRejectedError(
                    "SMTP server rejected the sender address "
                    f"{self.config.sender!r} (status={exc.smtp_code})."
                    f"{provider_hint}"
                ) from None

        return str(message["Message-ID"])

    def _attach_file(
        self,
        message: EmailMessage,
        path: Path,
    ) -> None:
        if not path.is_file():
            raise FileNotFoundError(f"Email attachment not found: {path}")

        content_type, encoding = mimetypes.guess_type(path.name)
        if content_type is None or encoding is not None:
            content_type = "application/octet-stream"

        main_type, sub_type = content_type.split("/", 1)
        message.add_attachment(
            path.read_bytes(),
            maintype=main_type,
            subtype=sub_type,
            filename=path.name,
        )
