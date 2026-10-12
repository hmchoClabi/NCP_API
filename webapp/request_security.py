"""요청마다 사용자 문맥을 구성하고 CSRF 계약을 검증한다."""

from __future__ import annotations

import hmac
from typing import Any, Protocol

from flask import Flask, abort, g, request

from webapp.security import token_hash


class SessionRepository(Protocol):
    """요청 보안 초기화에 필요한 최소 저장소 계약이다."""

    def session_user(self, session_token: str) -> dict[str, Any] | None: ...


def register_request_security(
    app: Flask,
    repository: SessionRepository,
    *,
    session_cookie: str,
    csrf_cookie: str,
) -> None:
    """사용자 로딩과 상태 변경 요청의 CSRF 검증을 등록한다.

    인증 저장소 접근과 요청 전 검증은 모든 라우트에 동일하게 적용되어야
    하므로 애플리케이션 조립 시 한 번만 등록한다. 기존 예외 endpoint와
    토큰 비교 방식은 보안 정책 호환을 위해 변경하지 않는다.
    """

    @app.before_request
    def load_user_and_validate_csrf() -> None:
        session_token = request.cookies.get(session_cookie, "")
        g.user = repository.session_user(session_token)
        g.csrf_token = request.cookies.get(csrf_cookie, "")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.endpoint in {"login", "health_live", "health_ready"}:
                return None
            submitted = request.form.get("csrf_token") or request.headers.get(
                "X-CSRF-Token",
                "",
            )
            expected_hash = g.user.get("csrf_token_hash") if g.user else ""
            if (
                not submitted
                or not expected_hash
                or not hmac.compare_digest(
                    token_hash(submitted),
                    expected_hash,
                )
            ):
                abort(403)
        return None
