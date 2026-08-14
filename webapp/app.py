from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from flask import Flask

from database.config import DatabaseSettings
from webapp.auth_routes import register_auth_routes
from webapp.jobs import ReportJobRepository
from webapp.msp_routes import register_msp_routes
from webapp.portal_routes import register_portal_routes
from webapp.presentation import KST, format_kst, register_presentation
from webapp.repository import PortalRepository
from webapp.request_security import register_request_security
from webapp.route_access import (
    MSP_ROLES,
    _account_return,
    _can_access_environment,
    _can_access_tenant,
    _can_manage_tenant,
    _is_msp,
    _login_required,
    _msp_admin_environment_scopes,
    _msp_admin_required,
    _msp_environment_scopes,
    _msp_required,
)


SESSION_COOKIE = "ncp_report_session"
CSRF_COOKIE = "ncp_report_csrf"


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """애플리케이션 의존성을 조립하고 역할별 라우트를 등록한다."""
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("WEB_SECRET_KEY", "local-development-only"),
        SESSION_COOKIE_SECURE=_as_bool(os.getenv("WEB_COOKIE_SECURE"), False),
        DATABASE_SETTINGS=DatabaseSettings.from_env(),
        CREDENTIAL_MASTER_KEY_FILE=os.getenv(
            "CREDENTIAL_MASTER_KEY_FILE",
            str(Path("secrets") / "credential-master-key"),
        ),
        APP_VERSION=os.getenv("APP_VERSION", "local"),
        APP_SOURCE_REVISION=os.getenv("APP_SOURCE_REVISION", ""),
        # multipart 오버헤드를 포함하되 512KB 로고 제한보다 충분히 작게 둔다.
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    repository = app.config.get("PORTAL_REPOSITORY") or PortalRepository(
        app.config["DATABASE_SETTINGS"]
    )
    app.extensions["portal_repository"] = repository
    jobs = app.config.get("REPORT_JOB_REPOSITORY") or ReportJobRepository(
        app.config["DATABASE_SETTINGS"]
    )
    app.extensions["report_job_repository"] = jobs

    register_presentation(app)
    register_request_security(
        app,
        repository,
        session_cookie=SESSION_COOKIE,
        csrf_cookie=CSRF_COOKIE,
    )
    register_auth_routes(
        app,
        repository,
        session_cookie=SESSION_COOKIE,
        csrf_cookie=CSRF_COOKIE,
    )
    register_msp_routes(app, repository, jobs)
    register_portal_routes(app, repository, jobs)
    return app


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


__all__ = [
    "CSRF_COOKIE",
    "KST",
    "MSP_ROLES",
    "SESSION_COOKIE",
    "_account_return",
    "_can_access_environment",
    "_can_access_tenant",
    "_can_manage_tenant",
    "_is_msp",
    "_login_required",
    "_msp_admin_environment_scopes",
    "_msp_admin_required",
    "_msp_environment_scopes",
    "_msp_required",
    "create_app",
    "format_kst",
]
