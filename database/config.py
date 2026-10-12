from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from dotenv import dotenv_values


ROLE_USERS = {
    "msp": ("ncp_msp_app", "DB_MSP_APP_PASSWORD"),
    "control": ("ncp_control_app", "DB_CONTROL_APP_PASSWORD"),
    "public_worker": ("ncp_public_worker", "DB_PUBLIC_WORKER_PASSWORD"),
    "gov_worker": ("ncp_gov_worker", "DB_GOV_WORKER_PASSWORD"),
}


def _as_bool(value: object, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Boolean setting has an invalid value: {value!r}")


def _positive_int(value: object, name: str, default: int) -> int:
    raw_value = default if value in (None, "") else value
    try:
        result = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if result <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return result


@dataclass(frozen=True, repr=False)
class DatabaseSettings:
    enabled: bool = False
    required: bool = True
    role: str = "msp"
    database_url: Optional[str] = None
    host: str = "127.0.0.1"
    port: int = 55432
    database: str = "ncp_report"
    username: str = "ncp_msp_app"
    password: str = ""
    sslmode: str = "disable"
    connect_timeout: int = 10
    application_name: str = "ncp-report-cli"
    tenant_id: Optional[str] = None

    @classmethod
    def from_env(
        cls,
        environ: Optional[Mapping[str, str]] = None,
        project_root: Optional[Path] = None,
    ) -> "DatabaseSettings":
        process_env = dict(os.environ if environ is None else environ)
        root = project_root or Path(__file__).resolve().parent.parent
        config_file = Path(process_env.get("REPORT_DB_CONFIG_FILE", ".env.db"))
        if not config_file.is_absolute():
            config_file = root / config_file

        file_values = {
            key: str(value)
            for key, value in (dotenv_values(config_file).items() if config_file.exists() else [])
            if value is not None
        }

        def setting(name: str, default: Optional[str] = None) -> Optional[str]:
            return process_env.get(name, file_values.get(name, default))

        role = str(setting("REPORT_DB_ROLE", "msp")).strip().casefold()
        if role not in ROLE_USERS:
            allowed = ", ".join(sorted(ROLE_USERS))
            raise ValueError(f"REPORT_DB_ROLE must be one of: {allowed}.")

        default_user, password_name = ROLE_USERS[role]
        settings = cls(
            enabled=_as_bool(setting("REPORT_DB_ENABLED"), False),
            required=_as_bool(setting("REPORT_DB_REQUIRED"), True),
            role=role,
            database_url=setting("REPORT_DATABASE_URL") or None,
            host=str(setting("REPORT_DB_HOST", setting("DB_HOST", "127.0.0.1"))),
            port=_positive_int(
                setting("REPORT_DB_PORT", setting("DB_PORT", "55432")),
                "REPORT_DB_PORT",
                55432,
            ),
            database=str(setting("REPORT_DB_NAME", setting("DB_NAME", "ncp_report"))),
            username=str(setting("REPORT_DB_USER", default_user)),
            password=str(setting("REPORT_DB_PASSWORD", setting(password_name, ""))),
            sslmode=str(setting("REPORT_DB_SSLMODE", "disable")).strip(),
            connect_timeout=_positive_int(
                setting("REPORT_DB_CONNECT_TIMEOUT", "10"),
                "REPORT_DB_CONNECT_TIMEOUT",
                10,
            ),
            application_name=str(setting("REPORT_DB_APPLICATION_NAME", "ncp-report-cli")).strip(),
            tenant_id=setting("REPORT_DB_TENANT_ID") or None,
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not self.enabled:
            return
        if not self.database_url and not self.password:
            raise ValueError(
                "Database storage is enabled but no database password is configured. "
                "Set REPORT_DATABASE_URL, REPORT_DB_PASSWORD, or the selected role "
                "password in REPORT_DB_CONFIG_FILE."
            )
        if self.sslmode not in {
            "disable",
            "allow",
            "prefer",
            "require",
            "verify-ca",
            "verify-full",
        }:
            raise ValueError("REPORT_DB_SSLMODE has an unsupported value.")
        if self.role == "control" and not self.tenant_id:
            raise ValueError("REPORT_DB_TENANT_ID is required for a tenant-scoped DB role.")

    def connection_kwargs(self) -> dict:
        common = {
            "connect_timeout": self.connect_timeout,
            "application_name": self.application_name,
        }
        if self.database_url:
            return {"conninfo": self.database_url, **common}
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.database,
            "user": self.username,
            "password": self.password,
            "sslmode": self.sslmode,
            **common,
        }

    def __repr__(self) -> str:
        location = "REPORT_DATABASE_URL" if self.database_url else f"{self.host}:{self.port}"
        return (
            "DatabaseSettings("
            f"enabled={self.enabled!r}, required={self.required!r}, "
            f"role={self.role!r}, location={location!r}, database={self.database!r}, "
            f"username={self.username!r}, password='***')"
        )
