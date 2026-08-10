"""웹 라우트가 공유하는 인증·고객 접근 경계를 정의한다."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import abort, g, redirect, url_for


MSP_ROLES = {"MSP_ADMIN", "MSP_OPERATOR", "SYSTEM_ADMIN"}


def _account_return(tenant_id: str):
    if _is_msp(g.user):
        return redirect(url_for("msp_customer", tenant_id=tenant_id))
    return redirect(url_for("customer_portal"))


def _login_required(view: Callable):
    """로그인 사용자만 라우트 본문에 진입하도록 한다."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.get("user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def _msp_required(view: Callable):
    """MSP 플랫폼 역할 보유자만 라우트 본문에 진입하도록 한다."""

    @wraps(view)
    @_login_required
    def wrapped(*args, **kwargs):
        if not _is_msp(g.user):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def _msp_admin_required(view: Callable):
    """고객·사용자 설정을 변경하는 기능을 MSP 관리자에게 제한한다."""

    @wraps(view)
    @_login_required
    def wrapped(*args, **kwargs):
        if "MSP_ADMIN" not in set(g.user.get("platform_roles", [])):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def _is_msp(user: dict[str, Any]) -> bool:
    return bool(set(user.get("platform_roles", [])) & MSP_ROLES)


def _can_access_tenant(user: dict[str, Any], tenant_id: str) -> bool:
    if _is_msp(user):
        return True
    return tenant_id in {
        str(item["tenant_id"]) for item in user.get("memberships", [])
    }


def _can_manage_tenant(user: dict[str, Any], tenant_id: str) -> bool:
    if "MSP_ADMIN" in set(user.get("platform_roles", [])):
        return True
    return any(
        str(item["tenant_id"]) == tenant_id
        and item.get("role") == "CUSTOMER_ADMIN"
        for item in user.get("memberships", [])
    )
