"""웹 라우트가 공유하는 인증·고객 접근 경계를 정의한다."""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import abort, g, redirect, url_for

MSP_ROLES = {"MSP_ADMIN", "MSP_OPERATOR", "SYSTEM_ADMIN"}
NCP_ENVIRONMENTS = {"public", "gov"}


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


def _msp_environment_scopes(user: dict[str, Any]) -> set[str] | None:
    """MSP 사용자의 접근 환경을 반환하며 ``None``은 전체 환경을 뜻한다.

    기존 세션/테스트처럼 상세 역할 바인딩이 없는 MSP 컨텍스트는 과거와
    호환되도록 전체 범위로 해석한다. 실제 DB 컨텍스트는 항상 바인딩을
    제공하므로, 환경이 지정된 계정은 명시된 환경으로만 제한된다.
    """

    return _platform_role_environment_scopes(user, MSP_ROLES)


def _msp_admin_environment_scopes(user: dict[str, Any]) -> set[str] | None:
    """MSP 관리자 역할 자체에 부여된 환경 범위를 반환한다."""

    return _platform_role_environment_scopes(user, {"MSP_ADMIN"})


def _platform_role_environment_scopes(
    user: dict[str, Any], role_names: set[str]
) -> set[str] | None:
    if not set(user.get("platform_roles", [])) & role_names:
        return set()
    bindings = user.get("platform_role_bindings")
    if bindings is None:
        return None
    relevant = [item for item in bindings if item.get("role") in role_names]
    if any(item.get("environment_scope") is None for item in relevant):
        return None
    return {
        str(item["environment_scope"])
        for item in relevant
        if item.get("environment_scope") in NCP_ENVIRONMENTS
    }


def _can_access_environment(user: dict[str, Any], environment: str) -> bool:
    if not _is_msp(user):
        return False
    scopes = _msp_environment_scopes(user)
    return scopes is None or environment in scopes


def _can_access_tenant(
    user: dict[str, Any],
    tenant_id: str,
    environment: str | None = None,
) -> bool:
    if _is_msp(user):
        scopes = _msp_environment_scopes(user)
        if scopes is None:
            return True
        return environment is not None and environment in scopes
    return tenant_id in {str(item["tenant_id"]) for item in user.get("memberships", [])}


def _can_manage_tenant(
    user: dict[str, Any],
    tenant_id: str,
    environment: str | None = None,
) -> bool:
    if "MSP_ADMIN" in set(user.get("platform_roles", [])):
        scopes = _msp_admin_environment_scopes(user)
        if scopes is None:
            return True
        return environment is not None and environment in scopes
    return any(
        str(item["tenant_id"]) == tenant_id and item.get("role") == "CUSTOMER_ADMIN"
        for item in user.get("memberships", [])
    )
