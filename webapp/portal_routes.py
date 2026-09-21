"""고객 포털과 보고서 조회·생성 라우트를 등록한다."""

from __future__ import annotations

import base64
import re
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, send_file, url_for

from webapp.presentation import format_kst
from app.renderers.html_styles import REPORT_DISPLAY_STYLES
from webapp.repository import _artifact_fingerprint, _local_report_artifact_paths
from webapp.route_access import (
    _account_return,
    _can_access_tenant,
    _can_manage_tenant,
    _is_msp,
    _login_required,
    _msp_environment_scopes,
    _msp_required,
)


def register_portal_routes(app: Flask, repository: Any, jobs: Any) -> None:
    """tenant 접근 권한을 유지하며 포털·보고서 endpoint를 등록한다."""

    def accessible_tenant_ids(user: dict[str, Any]) -> list[str] | None:
        if not _is_msp(user):
            return [
                str(item["tenant_id"])
                for item in user.get("memberships", [])
            ]
        scopes = _msp_environment_scopes(user)
        if scopes is None:
            return None
        return repository.tenant_ids_for_environments(scopes)

    def account_tenant(account_id: str) -> tuple[str, dict[str, Any]] | None:
        tenant_id = repository.account_tenant(account_id)
        if not tenant_id:
            return None
        tenant = repository.tenant_detail(tenant_id)
        if not tenant:
            return None
        return tenant_id, tenant

    @app.post("/accounts/<account_id>/report-jobs")
    @_login_required
    def enqueue_report(account_id: str):
        account_scope = account_tenant(account_id)
        if not account_scope:
            abort(404)
        tenant_id, tenant = account_scope
        if not _can_access_tenant(
            g.user, tenant_id, tenant.get("environment")
        ):
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
        account_scope = account_tenant(account_id)
        if not account_scope:
            abort(404)
        tenant_id, tenant = account_scope
        if not _can_manage_tenant(
            g.user, tenant_id, tenant.get("environment")
        ):
            abort(403)
        try:
            report_type = request.form.get("report_type", "")
            monthly_day_value = request.form.get("monthly_day", "").strip()
            weekly_day_value = request.form.get("weekly_day", "").strip()
            jobs.upsert_schedule(
                account_id,
                report_type,
                int(request.form.get("run_hour", "9")),
                int(request.form.get("run_minute", "0")),
                int(monthly_day_value) if monthly_day_value else None,
                str(g.user["id"]),
                weekly_day=(
                    int(weekly_day_value) if weekly_day_value else None
                ),
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
            customers = repository.tenants(
                allowed_environments=_msp_environment_scopes(g.user)
            )
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
        environment_by_tenant = {
            str(item.get("id", item.get("tenant_id"))): item.get("environment")
            for item in (customers or memberships)
        }
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
                tenant_id
                for tenant_id in tenant_ids
                if _can_manage_tenant(
                    g.user,
                    tenant_id,
                    environment_by_tenant.get(tenant_id),
                )
            },
        )

    @app.get("/reports/<report_id>")
    @_login_required
    def report_detail(report_id: str):
        allowed = accessible_tenant_ids(g.user)
        report = repository.report_detail(
            report_id,
            allowed,
            include_snapshot=False,
        )
        if not report:
            abort(404)
        return render_template(
            "report_detail.html",
            report=report,
            can_delete_report=_is_msp(g.user),
            report_display_styles=REPORT_DISPLAY_STYLES,
        )

    @app.post("/reports/<report_id>/delete")
    @_msp_required
    def delete_report(report_id: str):
        if not repository.report_detail(
            report_id,
            accessible_tenant_ids(g.user),
            include_snapshot=False,
        ):
            abort(404)
        try:
            deleted = repository.delete_report(report_id, str(g.user["id"]))
            message = f"{deleted['customer_name']} 보고서를 삭제했습니다."
            if deleted["failed_artifact_files"]:
                message += (
                    " 일부 산출물 파일은 삭제하지 못해 운영자 확인이 필요합니다."
                )
                flash(message, "warning")
            else:
                flash(message, "success")
            return redirect(
                url_for("msp_customer", tenant_id=deleted["tenant_id"])
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("customer_portal"))

    @app.get("/history")
    @_login_required
    def report_history():
        tenant_ids = accessible_tenant_ids(g.user)
        customers = (repository.tenants(allowed_environments=_msp_environment_scopes(g.user))
                     if _is_msp(g.user) else [
                         {"id": item["tenant_id"], "customer_name": item["customer_name"]}
                         for item in g.user.get("memberships", [])])
        selected_tenant = request.args.get("tenant_id", "").strip()
        if selected_tenant:
            if selected_tenant not in {str(item["id"]) for item in customers}:
                abort(404)
            tenant_ids = [selected_tenant]
        query = request.args.get("q", "").strip()[:200]
        status = request.args.get("status", "")
        statuses = {"QUEUED": "대기", "RUNNING": "실행 중", "SUCCESS": "성공",
                    "PARTIAL_SUCCESS": "부분 수집", "FAILED": "실패", "CANCELLED": "취소"}
        if status and status not in statuses:
            abort(400)
        try:
            page = int(request.args.get("page", "1"))
            if not 1 <= page <= 100000:
                raise ValueError
        except ValueError:
            abort(400)
        history = repository.report_history(tenant_ids, query=query, status=status,
                                            limit=51, offset=(page - 1) * 50)
        filters = {"tenant_id": selected_tenant, "q": query, "status": status}
        return render_template(
            "history.html",
            history=history[:50], customers=customers, filters=filters, statuses=statuses,
            page=page, previous_url=url_for("report_history", **filters, page=page - 1) if page > 1 else None,
            next_url=url_for("report_history", **filters, page=page + 1) if len(history) > 50 else None,
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
        tenant_ids = accessible_tenant_ids(g.user)
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
                event["status"],
                ("info", "보고서 작업 상태가 변경되었습니다."),
            )
            occurred_at = event["occurred_at"].astimezone(timezone.utc)
            payload.append(
                {
                    "id": (
                        f"{event['id']}:{event['status']}:"
                        f"{occurred_at.isoformat()}"
                    ),
                    "category": category,
                    "message": (
                        f"{action} {event['customer_name']} · "
                        f"{event['account_name']} · {event['report_type']}"
                    ),
                    "occurred_at": occurred_at.isoformat(),
                    "occurred_at_kst": format_kst(occurred_at),
                }
            )
        return jsonify(
            {
                "events": payload,
                "server_time": datetime.now(timezone.utc).isoformat(),
            }
        )

    @app.get("/reports/<report_id>/content")
    @_login_required
    def report_content(report_id: str):
        allowed = accessible_tenant_ids(g.user)
        artifact = repository.report_html_artifact(report_id, allowed)
        if not artifact:
            abort(404)
        try:
            paths, failed = _local_report_artifact_paths(
                [str(artifact["storage_uri"])],
                include_legacy=False,
                reject_outside=True,
            )
            if failed or len(paths) != 1:
                abort(404)
            path = next(iter(paths))
            actual_sha256, actual_size = _artifact_fingerprint(path)
            if (
                actual_sha256 != str(artifact["checksum_sha256"])
                or actual_size != int(artifact["byte_size"])
            ):
                abort(404)
            script_sources = " ".join(
                "'sha256-"
                + base64.b64encode(sha256(script).digest()).decode("ascii")
                + "'"
                for script in re.findall(
                    rb"<script(?:\s[^>]*)?>(.*?)</script>",
                    path.read_bytes(),
                    flags=re.IGNORECASE | re.DOTALL,
                )
            ) or "'none'"
        except (KeyError, OSError, TypeError, ValueError):
            abort(404)
        response = send_file(
            path,
            mimetype="text/html",
            conditional=True,
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; "
            f"script-src {script_sources}; "
            "img-src data: blob:; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
