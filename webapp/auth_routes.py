"""상태 확인과 포털 인증 라우트를 등록한다."""

from __future__ import annotations

import hmac
import secrets
from typing import Any, Protocol

from flask import Flask, abort, flash, g, redirect, render_template, request, url_for

from webapp.route_access import _is_msp, _login_required
from webapp.security import verify_password


class AuthRepository(Protocol):
    """인증 라우트가 사용하는 저장소 계약이다."""

    def tenants(self, environment: str | None = None) -> list[dict[str, Any]]: ...

    def authenticate(self, email: str) -> dict[str, Any] | None: ...

    def log_authentication(
        self,
        email: str,
        result: str,
        user_id: str | None = None,
        failure_reason: str | None = None,
    ) -> None: ...

    def create_session(self, user_id: str) -> tuple[str, str]: ...

    def user_context(self, user_id: str) -> dict[str, Any] | None: ...

    def revoke_session(self, session_token: str) -> None: ...


def register_auth_routes(
    app: Flask,
    repository: AuthRepository,
    *,
    session_cookie: str,
    csrf_cookie: str,
) -> None:
    """기존 endpoint 이름을 유지해 상태·로그인·로그아웃 라우트를 등록한다."""

    @app.get("/health/live")
    def health_live():
        return {"status": "ok"}

    @app.get("/health/ready")
    def health_ready():
        repository.tenants()
        return {"status": "ready"}

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            if g.get("user"):
                return redirect(url_for("index"))
            login_csrf = request.cookies.get(csrf_cookie) or secrets.token_urlsafe(32)
            response = app.make_response(
                render_template("login.html", csrf_token=login_csrf)
            )
            response.set_cookie(
                csrf_cookie,
                login_csrf,
                httponly=False,
                secure=app.config["SESSION_COOKIE_SECURE"],
                samesite="Lax",
                max_age=900,
            )
            return response
        submitted_csrf = request.form.get("csrf_token", "")
        cookie_csrf = request.cookies.get(csrf_cookie, "")
        if not submitted_csrf or not hmac.compare_digest(
            submitted_csrf,
            cookie_csrf,
        ):
            abort(403)
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = repository.authenticate(email)
        if not user or user["status"] != "ACTIVE" or not verify_password(
            user.get("password_hash") or "", password
        ):
            repository.log_authentication(
                email,
                "DENIED",
                failure_reason="INVALID_CREDENTIALS",
            )
            flash("이메일 또는 비밀번호를 확인해 주세요.", "error")
            return render_template("login.html"), 401
        repository.log_authentication(email, "SUCCESS", str(user["id"]))
        session_token, csrf_token = repository.create_session(str(user["id"]))
        context = repository.user_context(str(user["id"])) or {}
        destination = "msp_dashboard" if _is_msp(context) else "customer_portal"
        response = redirect(url_for(destination))
        response.set_cookie(
            session_cookie,
            session_token,
            httponly=True,
            secure=app.config["SESSION_COOKIE_SECURE"],
            samesite="Lax",
            max_age=43200,
        )
        response.set_cookie(
            csrf_cookie,
            csrf_token,
            httponly=False,
            secure=app.config["SESSION_COOKIE_SECURE"],
            samesite="Lax",
            max_age=43200,
        )
        return response

    @app.post("/logout")
    @_login_required
    def logout():
        repository.revoke_session(request.cookies.get(session_cookie, ""))
        response = redirect(url_for("login"))
        response.delete_cookie(session_cookie)
        response.delete_cookie(csrf_cookie)
        return response

    @app.get("/")
    @_login_required
    def index():
        return redirect(
            url_for("msp_dashboard" if _is_msp(g.user) else "customer_portal")
        )
