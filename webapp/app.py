from __future__ import annotations

import hmac
import os
import secrets
from functools import wraps
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

from flask import (
    Flask, Response, abort, flash, g, jsonify, redirect, render_template, request,
    url_for,
)

from app.renderers import HtmlReportRenderer
from app.report_models import ReportResult
from database.config import DatabaseSettings
from webapp.repository import PortalRepository
from webapp.jobs import ReportJobRepository
from webapp.security import (
    CredentialCipher,
    LocalKeyEncryptionProvider,
    token_hash,
    verify_password,
)


SESSION_COOKIE = "ncp_report_session"
CSRF_COOKIE = "ncp_report_csrf"
MSP_ROLES = {"MSP_ADMIN", "MSP_OPERATOR", "SYSTEM_ADMIN"}
KST = ZoneInfo("Asia/Seoul")


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
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

    @app.template_filter("kst")
    def format_kst(value: Any, format_string: str = "%Y-%m-%d %H:%M:%S") -> str:
        if value is None:
            return "-"
        parsed = value
        if isinstance(parsed, str):
            try:
                parsed = datetime.fromisoformat(parsed)
            except ValueError:
                return parsed
        if not isinstance(parsed, datetime):
            return str(parsed)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return f"{parsed.astimezone(KST).strftime(format_string)} KST"

    @app.template_filter("duration")
    def format_duration(value: Any) -> str:
        if value is None:
            return "-"
        try:
            total_seconds = max(int(value), 0)
        except (TypeError, ValueError, OverflowError):
            return str(value)
        days, remainder = divmod(total_seconds, 86_400)
        hours, remainder = divmod(remainder, 3_600)
        minutes, seconds = divmod(remainder, 60)
        parts = []
        if days:
            parts.append(f"{days}일")
        if hours:
            parts.append(f"{hours}시간")
        if minutes:
            parts.append(f"{minutes}분")
        if seconds or not parts:
            parts.append(f"{seconds}초")
        return " ".join(parts)

    @app.template_filter("inclusive_end")
    def inclusive_period_end(value: Any, end_exclusive: Any = True) -> Any:
        exclusive = (
            end_exclusive
            if isinstance(end_exclusive, bool)
            else _as_bool(end_exclusive, True)
            if isinstance(end_exclusive, str)
            else True
        )
        if value is None or not exclusive:
            return value
        parsed = value
        if isinstance(parsed, str):
            try:
                parsed = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
            except ValueError:
                return value
        if not isinstance(parsed, datetime):
            return value
        return parsed - timedelta(microseconds=1)

    @app.before_request
    def load_user_and_validate_csrf():
        session_token = request.cookies.get(SESSION_COOKIE, "")
        g.user = repository.session_user(session_token)
        g.csrf_token = request.cookies.get(CSRF_COOKIE, "")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.endpoint in {"login", "health_live", "health_ready"}:
                return None
            submitted = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
            expected_hash = g.user.get("csrf_token_hash") if g.user else ""
            if not submitted or not expected_hash or not hmac.compare_digest(
                token_hash(submitted), expected_hash
            ):
                abort(403)
        return None

    @app.context_processor
    def template_context():
        now = datetime.now(KST)
        today = now.date()
        previous_month_end = today.replace(day=1) - timedelta(days=1)
        return {
            "current_user": g.get("user"),
            "csrf_token": g.get("csrf_token", ""),
            "default_daily_target": (today - timedelta(days=1)).isoformat(),
            "default_monthly_target": previous_month_end.strftime("%Y-%m"),
            "default_range_start": (
                now.replace(second=0, microsecond=0) - timedelta(hours=1)
            ).strftime("%Y-%m-%dT%H:%M"),
            "default_range_end": now.replace(
                second=0, microsecond=0
            ).strftime("%Y-%m-%dT%H:%M"),
            "notification_since": datetime.now(timezone.utc).isoformat(),
            "app_version": str(app.config["APP_VERSION"]),
            "app_source_revision": str(
                app.config["APP_SOURCE_REVISION"]
            ),
        }

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
            login_csrf = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
            response = app.make_response(
                render_template("login.html", csrf_token=login_csrf)
            )
            response.set_cookie(
                CSRF_COOKIE, login_csrf, httponly=False,
                secure=app.config["SESSION_COOKIE_SECURE"], samesite="Lax",
                max_age=900,
            )
            return response
        submitted_csrf = request.form.get("csrf_token", "")
        cookie_csrf = request.cookies.get(CSRF_COOKIE, "")
        if not submitted_csrf or not hmac.compare_digest(submitted_csrf, cookie_csrf):
            abort(403)
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        user = repository.authenticate(email)
        if not user or user["status"] != "ACTIVE" or not verify_password(
            user.get("password_hash") or "", password
        ):
            repository.log_authentication(email, "DENIED", failure_reason="INVALID_CREDENTIALS")
            flash("이메일 또는 비밀번호를 확인해 주세요.", "error")
            return render_template("login.html"), 401
        repository.log_authentication(email, "SUCCESS", str(user["id"]))
        session_token, csrf_token = repository.create_session(str(user["id"]))
        context = repository.user_context(str(user["id"])) or {}
        destination = "msp_dashboard" if _is_msp(context) else "customer_portal"
        response = redirect(url_for(destination))
        response.set_cookie(
            SESSION_COOKIE, session_token, httponly=True,
            secure=app.config["SESSION_COOKIE_SECURE"], samesite="Lax", max_age=43200,
        )
        response.set_cookie(
            CSRF_COOKIE, csrf_token, httponly=False,
            secure=app.config["SESSION_COOKIE_SECURE"], samesite="Lax", max_age=43200,
        )
        return response

    @app.post("/logout")
    @_login_required
    def logout():
        repository.revoke_session(request.cookies.get(SESSION_COOKIE, ""))
        response = redirect(url_for("login"))
        response.delete_cookie(SESSION_COOKIE)
        response.delete_cookie(CSRF_COOKIE)
        return response

    @app.get("/")
    @_login_required
    def index():
        return redirect(url_for("msp_dashboard" if _is_msp(g.user) else "customer_portal"))

    @app.get("/msp")
    @_msp_required
    def msp_dashboard():
        return render_template("msp_dashboard.html", **repository.dashboard())

    @app.get("/msp/customers/<environment>")
    @_msp_required
    def msp_customers(environment: str):
        if environment not in {"public", "gov"}:
            abort(404)
        return render_template(
            "customers.html",
            customers=repository.tenants(environment),
            environment=environment,
        )

    @app.get("/msp/schedules")
    @_msp_required
    def msp_schedules():
        return render_template(
            "schedules.html",
            schedules=repository.schedules(),
            schedule_accounts=repository.schedulable_accounts(),
        )

    @app.get("/msp/users")
    @_msp_admin_required
    def msp_users():
        return render_template(
            "users.html",
            users=repository.customer_users(),
            msp_users=repository.msp_users(),
            customers=repository.tenants(),
            selected_tenant_id=request.args.get("tenant_id", ""),
        )

    @app.post("/msp/users")
    @_msp_admin_required
    def create_portal_user():
        try:
            password = request.form.get("password", "")
            if password != request.form.get("password_confirmation", ""):
                raise ValueError("비밀번호 확인이 일치하지 않습니다.")
            repository.create_portal_user(
                request.form.get("email", ""),
                password,
                request.form.get("display_name", ""),
            )
            flash("사용자를 등록했습니다. 고객사에 연결하면 로그인이 활성화됩니다.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_users"))

    @app.post("/msp/users/platform")
    @_msp_admin_required
    def create_msp_user():
        try:
            password = request.form.get("password", "")
            if password != request.form.get("password_confirmation", ""):
                raise ValueError("비밀번호 확인이 일치하지 않습니다.")
            repository.create_msp_user(
                request.form.get("email", ""),
                password,
                request.form.get("display_name", ""),
                request.form.get("role", "MSP_OPERATOR"),
            )
            flash("MSP 계정을 등록했습니다.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_users"))

    @app.post("/msp/users/memberships")
    @_msp_admin_required
    def assign_portal_user():
        try:
            repository.assign_customer_membership(
                request.form.get("user_id", ""),
                request.form.get("tenant_id", ""),
                request.form.get("role", "CUSTOMER_VIEWER"),
            )
            flash("사용자와 고객사를 연결했습니다.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_users"))

    @app.post("/msp/schedules/<schedule_id>/enabled")
    @_msp_admin_required
    def set_schedule_enabled(schedule_id: str):
        enabled = request.form.get("enabled") == "true"
        if not jobs.set_schedule_enabled(schedule_id, enabled):
            abort(404)
        flash("자동 실행 일정 상태를 변경했습니다.", "success")
        return redirect(url_for("msp_schedules"))

    @app.post("/msp/schedules/bulk")
    @_msp_admin_required
    def bulk_schedules():
        try:
            action = request.form.get("action", "create")
            account_ids = request.form.getlist("account_id")
            report_type = request.form.get("report_type", "DAILY")
            if action == "delete":
                count = jobs.bulk_delete_schedules(account_ids, report_type)
                flash(f"선택한 일정 {count}개를 삭제했습니다.", "success")
            elif action == "create":
                try:
                    run_hour = int(request.form.get("run_hour", "9"))
                    run_minute = int(request.form.get("run_minute", "0"))
                    monthly_day_text = request.form.get("monthly_day", "1")
                    monthly_day = int(monthly_day_text)
                except (TypeError, ValueError) as exc:
                    raise ValueError("실행 시각 또는 월간 실행일이 올바르지 않습니다.") from exc
                count = jobs.bulk_upsert_schedules(
                    account_ids, report_type, run_hour, run_minute,
                    monthly_day, str(g.user["id"]),
                )
                flash(f"선택한 계정 {count}개에 일정을 적용했습니다.", "success")
            else:
                raise ValueError("지원하지 않는 일정 작업입니다.")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_schedules"))

    @app.post("/msp/customers/<environment>")
    @_msp_admin_required
    def create_customer(environment: str):
        try:
            tenant_id = repository.create_tenant(
                request.form.get("customer_code", ""),
                request.form.get("customer_name", ""),
                environment,
                request.form.get("region", "KRS" if environment == "gov" else "KR"),
            )
            flash("고객사를 등록했습니다.", "success")
            return redirect(url_for("msp_customer", tenant_id=tenant_id))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("msp_customers", environment=environment))

    @app.get("/msp/customer/<tenant_id>")
    @_msp_required
    def msp_customer(tenant_id: str):
        tenant = repository.tenant_detail(tenant_id)
        if not tenant:
            abort(404)
        return render_template(
            "customer_detail.html",
            tenant=tenant,
            tenant_users=(
                repository.users_for_tenant(tenant_id)
                if "MSP_ADMIN" in set(g.user.get("platform_roles", [])) else []
            ),
            reports=tenant["reports"],
            jobs=repository.jobs_for_tenants([tenant_id]),
            can_manage_schedules=_can_manage_tenant(g.user, tenant_id),
            can_delete_reports=True,
        )

    @app.post("/msp/customer/<tenant_id>/credentials")
    @_msp_admin_required
    def register_credential(tenant_id: str):
        try:
            provider = LocalKeyEncryptionProvider(
                app.config["CREDENTIAL_MASTER_KEY_FILE"]
            )
            repository.register_account_credential(
                tenant_id=tenant_id,
                account_code=request.form.get("account_code", ""),
                display_name=request.form.get("display_name", ""),
                access_key=request.form.get("access_key", ""),
                secret_key=request.form.get("secret_key", ""),
                cipher=CredentialCipher(provider),
                actor_id=str(g.user["id"]),
            )
            flash("NCP 계정과 암호화된 API 키를 저장했습니다.", "success")
        except (RuntimeError, ValueError) as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_customer", tenant_id=tenant_id))

    @app.post("/msp/customer/<tenant_id>/credentials/<account_id>/delete")
    @_msp_admin_required
    def delete_credential(tenant_id: str, account_id: str):
        try:
            tenant = repository.tenant_detail(tenant_id)
            account = next(
                (
                    item for item in (tenant or {}).get("accounts", [])
                    if str(item["id"]) == account_id
                ),
                None,
            )
            confirmation = request.form.get("confirm_account_code", "").strip()
            if not account or confirmation != account["account_code"]:
                raise ValueError("삭제 확인을 위해 계정 코드를 정확히 입력하세요.")
            account_name = repository.delete_account_credential(
                tenant_id, account_id, str(g.user["id"])
            )
            flash(f"{account_name}의 API 키를 삭제하고 계정을 중지했습니다.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_customer", tenant_id=tenant_id))

    @app.post("/msp/customer/<tenant_id>/delete")
    @_msp_admin_required
    def delete_customer(tenant_id: str):
        try:
            tenant = repository.tenant_detail(tenant_id)
            confirmation = request.form.get("confirm_customer_code", "").strip()
            if not tenant or confirmation != tenant["customer_code"]:
                raise ValueError("삭제 확인을 위해 고객 코드를 정확히 입력하세요.")
            customer_name = repository.offboard_tenant(
                tenant_id, str(g.user["id"])
            )
            flash(
                f"{customer_name} 고객을 비활성화하고 저장된 API 키를 삭제했습니다.",
                "success",
            )
            return redirect(
                url_for("msp_customers", environment=tenant["environment"])
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("msp_customer", tenant_id=tenant_id))

    @app.post("/msp/customer/<tenant_id>/reactivate")
    @_msp_admin_required
    def reactivate_customer(tenant_id: str):
        try:
            tenant = repository.tenant_detail(tenant_id)
            confirmation = request.form.get("confirm_customer_code", "").strip()
            if not tenant or confirmation != tenant["customer_code"]:
                raise ValueError("재활성화 확인을 위해 고객 코드를 정확히 입력하세요.")
            customer_name = repository.reactivate_tenant(
                tenant_id, str(g.user["id"])
            )
            flash(
                f"{customer_name} 고객을 재활성화했습니다. API 키와 사용자 권한을 다시 등록하세요.",
                "success",
            )
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_customer", tenant_id=tenant_id))

    @app.post("/msp/customer/<tenant_id>/anonymize")
    @_msp_admin_required
    def anonymize_customer(tenant_id: str):
        try:
            tenant = repository.tenant_detail(tenant_id)
            code = request.form.get("confirm_customer_code", "").strip()
            phrase = request.form.get("confirm_phrase", "").strip()
            if not tenant or code != tenant["customer_code"] or phrase != "익명화":
                raise ValueError("고객 코드와 확인 문구 '익명화'를 정확히 입력하세요.")
            anonymous_name = repository.anonymize_tenant(
                tenant_id, str(g.user["id"])
            )
            flash(
                f"고객 개인정보를 {anonymous_name}(으)로 익명화했습니다. 이 작업은 되돌릴 수 없습니다.",
                "success",
            )
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_customer", tenant_id=tenant_id))

    @app.post("/msp/customer/<tenant_id>/permanent-delete")
    @_msp_admin_required
    def permanently_delete_customer(tenant_id: str):
        tenant = repository.tenant_detail(tenant_id)
        if not tenant:
            abort(404)
        try:
            code = request.form.get("confirm_customer_code", "").strip()
            phrase = request.form.get("confirm_phrase", "").strip()
            force = request.form.get("force_delete") == "true"
            expected_phrase = "강제 삭제" if force else "영구 삭제"
            if code != tenant["customer_code"] or phrase != expected_phrase:
                raise ValueError(
                    f"고객 코드와 확인 문구 '{expected_phrase}'를 정확히 입력하세요."
                )
            customer_name, report_count = repository.permanently_delete_tenant(
                tenant_id,
                str(g.user["id"]),
                request.form.get("archive_reference", ""),
                force=force,
            )
            deletion_type = "강제 삭제" if force else "영구 삭제"
            flash(
                f"{customer_name} 고객을 {deletion_type}했습니다. "
                f"삭제된 보고서 {report_count}건의 원장은 보존됩니다.",
                "success",
            )
            return redirect(
                url_for("msp_customers", environment=tenant["environment"])
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("msp_customer", tenant_id=tenant_id))

    @app.post("/accounts/<account_id>/report-jobs")
    @_login_required
    def enqueue_report(account_id: str):
        tenant_id = repository.account_tenant(account_id)
        if not tenant_id or not _can_access_tenant(g.user, tenant_id):
            abort(404)
        try:
            jobs.enqueue(
                account_id,
                request.form.get("report_type", ""),
                request.form.get("target_value", ""),
                str(g.user["id"]),
                start_datetime=request.form.get("start_datetime"),
                end_datetime=request.form.get("end_datetime"),
            )
            flash("보고서 생성 요청을 작업 큐에 등록했습니다.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return _account_return(tenant_id)

    @app.post("/accounts/<account_id>/schedules")
    @_login_required
    def save_schedule(account_id: str):
        tenant_id = repository.account_tenant(account_id)
        if not tenant_id or not _can_manage_tenant(g.user, tenant_id):
            abort(403)
        try:
            report_type = request.form.get("report_type", "")
            monthly_day_value = request.form.get("monthly_day", "").strip()
            jobs.upsert_schedule(
                account_id,
                report_type,
                int(request.form.get("run_hour", "9")),
                int(request.form.get("run_minute", "0")),
                int(monthly_day_value) if monthly_day_value else None,
                str(g.user["id"]),
            )
            flash("자동 보고서 일정을 저장했습니다.", "success")
        except (TypeError, ValueError) as exc:
            flash(str(exc), "error")
        return _account_return(tenant_id)

    @app.get("/portal")
    @_login_required
    def customer_portal():
        portal_is_msp = _is_msp(g.user)
        customers = []
        if portal_is_msp:
            customers = repository.tenants()
            tenant_ids = [str(item["id"]) for item in customers]
            memberships = [
                {
                    "tenant_id": item["id"],
                    "customer_name": item["customer_name"],
                    "environment": item["environment"],
                    "role": "MSP",
                }
                for item in customers
            ]
        else:
            memberships = g.user.get("memberships", [])
            tenant_ids = [str(item["tenant_id"]) for item in memberships]
        return render_template(
            "customer_portal.html",
            customers=customers,
            memberships=memberships,
            accounts=repository.accounts_for_tenants(tenant_ids),
            reports=repository.reports_for_tenants(tenant_ids),
            jobs=repository.jobs_for_tenants(tenant_ids),
            portal_is_msp=portal_is_msp,
            can_delete_reports=portal_is_msp,
            manageable_tenant_ids={
                tenant_id for tenant_id in tenant_ids
                if _can_manage_tenant(g.user, tenant_id)
            },
        )

    @app.get("/reports/<report_id>")
    @_login_required
    def report_detail(report_id: str):
        allowed = None if _is_msp(g.user) else [
            str(item["tenant_id"]) for item in g.user.get("memberships", [])
        ]
        report = repository.report_detail(report_id, allowed)
        if not report:
            abort(404)
        return render_template(
            "report_detail.html",
            report=report,
            can_delete_report=_is_msp(g.user),
        )

    @app.post("/reports/<report_id>/delete")
    @_msp_required
    def delete_report(report_id: str):
        try:
            deleted = repository.delete_report(report_id, str(g.user["id"]))
            message = f"{deleted['customer_name']} 보고서를 삭제했습니다."
            if deleted["failed_artifact_files"]:
                message += " 일부 산출물 파일은 삭제하지 못해 운영자 확인이 필요합니다."
                flash(message, "warning")
            else:
                flash(message, "success")
            return redirect(url_for(
                "msp_customer", tenant_id=deleted["tenant_id"]
            ))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("customer_portal"))

    @app.get("/history")
    @_login_required
    def report_history():
        tenant_ids = None if _is_msp(g.user) else [
            str(item["tenant_id"]) for item in g.user.get("memberships", [])
        ]
        return render_template(
            "history.html",
            history=repository.report_history(tenant_ids),
            is_msp=_is_msp(g.user),
        )

    @app.get("/notifications")
    @_login_required
    def notifications():
        after_text = request.args.get("after", "").strip()
        try:
            after = datetime.fromisoformat(after_text)
            if after.tzinfo is None:
                after = after.replace(tzinfo=timezone.utc)
            after = after.astimezone(timezone.utc)
        except (TypeError, ValueError):
            after = datetime.now(timezone.utc) - timedelta(seconds=10)
        oldest = datetime.now(timezone.utc) - timedelta(hours=24)
        if after < oldest:
            after = oldest
        tenant_ids = None if _is_msp(g.user) else [
            str(item["tenant_id"]) for item in g.user.get("memberships", [])
        ]
        labels = {
            "QUEUED": ("info", "보고서 작업이 등록되었습니다."),
            "RUNNING": ("info", "보고서 작업을 시작했습니다."),
            "SUCCESS": ("success", "보고서 작업이 완료되었습니다."),
            "FAILED": ("error", "보고서 작업이 실패했습니다."),
            "CANCELLED": ("warning", "보고서 작업이 취소되었습니다."),
        }
        payload = []
        for event in repository.notification_events(tenant_ids, after):
            category, action = labels.get(
                event["status"], ("info", "보고서 작업 상태가 변경되었습니다.")
            )
            occurred_at = event["occurred_at"].astimezone(timezone.utc)
            payload.append({
                "id": f"{event['id']}:{event['status']}:{occurred_at.isoformat()}",
                "category": category,
                "message": (
                    f"{action} {event['customer_name']} · "
                    f"{event['account_name']} · {event['report_type']}"
                ),
                "occurred_at": occurred_at.isoformat(),
                "occurred_at_kst": format_kst(occurred_at),
            })
        return jsonify({
            "events": payload,
            "server_time": datetime.now(timezone.utc).isoformat(),
        })

    @app.get("/reports/<report_id>/content")
    @_login_required
    def report_content(report_id: str):
        allowed = None if _is_msp(g.user) else [
            str(item["tenant_id"]) for item in g.user.get("memberships", [])
        ]
        report = repository.report_detail(report_id, allowed)
        if not report:
            abort(404)
        try:
            result = ReportResult.from_dict(report.get("snapshot") or {})
        except ValueError:
            abort(404)
        response = Response(
            HtmlReportRenderer().render(result),
            content_type="text/html; charset=utf-8",
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    return app


def _account_return(tenant_id: str):
    if _is_msp(g.user):
        return redirect(url_for("msp_customer", tenant_id=tenant_id))
    return redirect(url_for("customer_portal"))


def _login_required(view: Callable):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.get("user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def _msp_required(view: Callable):
    @wraps(view)
    @_login_required
    def wrapped(*args, **kwargs):
        if not _is_msp(g.user):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _msp_admin_required(view: Callable):
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


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}
