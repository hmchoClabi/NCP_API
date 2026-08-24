"""MSP 운영자용 고객·사용자·일정 관리 라우트를 등록한다."""

from __future__ import annotations

from typing import Any

from flask import Flask, abort, flash, g, redirect, render_template, request, url_for

from app.report_branding import MAX_CUSTOMER_LOGO_BYTES, validate_customer_logo
from app.report_options import (
    MONITORING_CATEGORY_OPTIONS,
    REPORT_SECTION_DESCRIPTIONS,
    REPORT_SECTION_LABELS,
    RESOURCE_CATEGORY_LABELS,
    RESOURCE_CATEGORY_OPTIONS,
    default_report_options,
)
from webapp.logo_fetcher import fetch_customer_logo_from_url
from webapp.route_access import (
    _can_access_environment,
    _can_access_tenant,
    _can_manage_tenant,
    _msp_admin_environment_scopes,
    _msp_admin_required,
    _msp_environment_scopes,
    _msp_required,
)
from webapp.security import CredentialCipher, LocalKeyEncryptionProvider


CUSTOMER_DETAIL_RECENT_LIMIT = 10
DATA_CLEANUP_CONFIRM_PHRASE = "선택 보고서 삭제"
DATA_CLEANUP_MAX_SELECTION = 500
RETENTION_BULK_MAX_SELECTION = 500
RETENTION_REPORT_TYPES = ("DAILY", "WEEKLY", "MONTHLY")


def register_msp_routes(app: Flask, repository: Any, jobs: Any) -> None:
    """MSP 역할 경계가 필요한 관리 라우트를 기존 endpoint로 등록한다."""

    def tenant_for_request(tenant_id: str, *, manage: bool = False) -> dict[str, Any]:
        tenant = repository.tenant_detail(tenant_id)
        permission_check = _can_manage_tenant if manage else _can_access_tenant
        if not tenant or not permission_check(
            g.user, tenant_id, tenant.get("environment")
        ):
            abort(404)
        return tenant

    def retention_policies_from_form() -> dict[str, dict[str, Any]]:
        return {
            report_type: {
                "mode": request.form.get(
                    f"retention_{report_type.lower()}_mode", "FOREVER"
                ),
                "days": request.form.get(
                    f"retention_{report_type.lower()}_days"
                ) or None,
            }
            for report_type in RETENTION_REPORT_TYPES
        }

    def active_retention_customers() -> list[dict[str, Any]]:
        return [
            customer
            for customer in repository.tenants(
                allowed_environments=_msp_admin_environment_scopes(g.user)
            )
            if customer.get("status") == "ACTIVE"
        ]

    @app.get("/msp")
    @_msp_required
    def msp_dashboard():
        return render_template(
            "msp_dashboard.html",
            **repository.dashboard(_msp_environment_scopes(g.user)),
        )

    @app.get("/msp/data-cleanup")
    @_msp_admin_required
    def msp_data_cleanup():
        reports = repository.report_cleanup_candidates(
            _msp_admin_environment_scopes(g.user)
        )
        eligible = [report for report in reports if report["eligible"]]
        return render_template(
            "data_cleanup.html",
            reports=reports,
            summary={
                "eligible_reports": len(eligible),
                "protected_reports": len(reports) - len(eligible),
                "artifact_count": sum(
                    int(report.get("artifact_count") or 0)
                    for report in eligible
                ),
                "artifact_bytes": sum(
                    int(report.get("artifact_bytes") or 0)
                    for report in eligible
                ),
            },
            confirm_phrase=DATA_CLEANUP_CONFIRM_PHRASE,
            max_selection=DATA_CLEANUP_MAX_SELECTION,
        )

    @app.post("/msp/data-cleanup")
    @_msp_admin_required
    def run_data_cleanup():
        try:
            if request.form.get("confirm_phrase", "").strip() != (
                DATA_CLEANUP_CONFIRM_PHRASE
            ):
                raise ValueError(
                    f"확인 문구 '{DATA_CLEANUP_CONFIRM_PHRASE}'를 정확히 입력하세요."
                )
            selection_scope = request.form.get(
                "selection_scope", "selected"
            ).strip().casefold()
            if selection_scope not in {"selected", "all"}:
                raise ValueError("정리 요청 범위가 올바르지 않습니다.")
            report_ids = list(dict.fromkeys(
                report_id.strip()
                for report_id in request.form.getlist("report_id")
                if report_id.strip()
            ))
            if selection_scope == "selected" and not report_ids:
                raise ValueError("정리할 보고서를 하나 이상 선택하세요.")
            if len(report_ids) > DATA_CLEANUP_MAX_SELECTION:
                raise ValueError(
                    f"한 번에 최대 {DATA_CLEANUP_MAX_SELECTION}건까지 "
                    "정리 요청할 수 있습니다."
                )

            result = repository.request_report_cleanup(
                report_ids if selection_scope == "selected" else None,
                str(g.user["id"]),
                allowed_environments=_msp_admin_environment_scopes(g.user),
                all_eligible=selection_scope == "all",
            )
            queued = int(result.get("queued_count") or 0)
            already_queued = int(result.get("already_queued_count") or 0)
            protected = int(result.get("protected_count") or 0)
            message = f"보고서 {queued}건의 백그라운드 정리를 요청했습니다."
            if already_queued:
                message += f" 이미 요청된 {already_queued}건은 중복 등록하지 않았습니다."
            if protected:
                message += f" 보호 대상 {protected}건은 제외했습니다."
            flash(
                message,
                "warning" if not queued or already_queued or protected else "success",
            )
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_data_cleanup"))

    @app.get("/msp/customers/<environment>")
    @_msp_required
    def msp_customers(environment: str):
        if environment not in {"public", "gov"}:
            abort(404)
        if not _can_access_environment(g.user, environment):
            abort(404)
        return render_template(
            "customers.html",
            customers=repository.tenants(
                environment,
                allowed_environments=_msp_environment_scopes(g.user),
            ),
            environment=environment,
        )

    @app.get("/msp/schedules")
    @_msp_required
    def msp_schedules():
        scopes = _msp_environment_scopes(g.user)
        admin_scopes = _msp_admin_environment_scopes(g.user)
        can_manage = "MSP_ADMIN" in set(g.user.get("platform_roles", []))
        return render_template(
            "schedules.html",
            schedules=repository.schedules(scopes),
            schedule_accounts=repository.schedulable_accounts(admin_scopes),
            retention_customers=(
                active_retention_customers() if can_manage else []
            ),
            manageable_environment_scopes=admin_scopes,
        )

    @app.post("/msp/report-retention/bulk")
    @_msp_admin_required
    def bulk_report_retention():
        try:
            tenant_ids = list(dict.fromkeys(
                tenant_id.strip()
                for tenant_id in request.form.getlist("tenant_id")
                if tenant_id.strip()
            ))
            if not tenant_ids:
                raise ValueError("보존 정책을 적용할 고객을 하나 이상 선택하세요.")
            if len(tenant_ids) > RETENTION_BULK_MAX_SELECTION:
                raise ValueError(
                    f"한 번에 최대 {RETENTION_BULK_MAX_SELECTION}개 고객까지 "
                    "적용할 수 있습니다."
                )
            allowed_ids = {
                str(customer["id"])
                for customer in active_retention_customers()
            }
            if not set(tenant_ids).issubset(allowed_ids):
                abort(403)
            count = repository.bulk_update_report_retention(
                tenant_ids,
                retention_policies_from_form(),
                str(g.user["id"]),
                allowed_environments=_msp_admin_environment_scopes(g.user),
            )
            flash(f"선택한 고객 {count}곳에 보존 정책을 적용했습니다.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_schedules"))

    @app.get("/msp/users")
    @_msp_admin_required
    def msp_users():
        scopes = _msp_admin_environment_scopes(g.user)
        return render_template(
            "users.html",
            users=repository.customer_users(scopes),
            msp_users=repository.msp_users(scopes),
            customers=repository.tenants(allowed_environments=scopes),
            selected_tenant_id=request.args.get("tenant_id", ""),
            allowed_environment_scopes=scopes,
        )

    @app.post("/msp/users")
    @_msp_admin_required
    def create_portal_user():
        if _msp_admin_environment_scopes(g.user) is not None:
            abort(403)
        try:
            password = request.form.get("password", "")
            if password != request.form.get("password_confirmation", ""):
                raise ValueError("비밀번호 확인이 일치하지 않습니다.")
            repository.create_portal_user(
                request.form.get("email", ""),
                password,
                request.form.get("display_name", ""),
            )
            flash(
                "사용자를 등록했습니다. 고객사에 연결하면 로그인이 활성화됩니다.",
                "success",
            )
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
            requested_scope = request.form.get(
                "environment_scope", ""
            ).strip().casefold() or None
            actor_scopes = _msp_admin_environment_scopes(g.user)
            if actor_scopes is not None and requested_scope not in actor_scopes:
                abort(403)
            repository.create_msp_user(
                request.form.get("email", ""),
                password,
                request.form.get("display_name", ""),
                request.form.get("role", "MSP_OPERATOR"),
                environment_scope=requested_scope,
                actor_id=str(g.user["id"]),
            )
            flash("MSP 계정을 등록했습니다.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_users"))

    @app.post("/msp/users/platform/<user_id>/enabled")
    @_msp_admin_required
    def set_msp_user_enabled(user_id: str):
        try:
            actor_scopes = _msp_admin_environment_scopes(g.user)
            if actor_scopes is not None:
                target_scopes = repository.msp_user_environment_scopes(user_id)
                if target_scopes is None or not target_scopes.issubset(actor_scopes):
                    abort(404)
            enabled_value = request.form.get("enabled", "").strip().casefold()
            if enabled_value not in {"true", "false"}:
                raise ValueError("MSP 계정 상태 요청이 올바르지 않습니다.")
            if user_id == str(g.user["id"]):
                raise ValueError(
                    "현재 로그인한 자신의 MSP 계정 상태는 변경할 수 없습니다."
                )
            display_name = repository.set_msp_user_enabled(
                user_id,
                str(g.user["id"]),
                enabled_value == "true",
            )
            action = "활성화" if enabled_value == "true" else "비활성화"
            flash(f"{display_name} MSP 계정을 {action}했습니다.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_users"))

    @app.post("/msp/users/<user_id>/delete")
    @_msp_admin_required
    def delete_user_account(user_id: str):
        try:
            if user_id == str(g.user["id"]):
                raise ValueError(
                    "현재 로그인한 자신의 계정은 삭제할 수 없습니다."
                )
            display_name, account_type = repository.delete_user_account(
                user_id,
                str(g.user["id"]),
                request.form.get("confirm_email", ""),
                allowed_environments=_msp_admin_environment_scopes(g.user),
            )
            label = "MSP" if account_type == "MSP" else "고객"
            flash(
                f"{display_name} {label} 계정을 삭제했습니다. "
                "모든 세션과 권한을 제거하고 개인정보를 익명화했습니다.",
                "success",
            )
        except PermissionError:
            abort(404)
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_users"))

    @app.post("/msp/users/memberships")
    @_msp_admin_required
    def assign_portal_user():
        try:
            tenant_id = request.form.get("tenant_id", "")
            tenant_for_request(tenant_id, manage=True)
            actor_scopes = _msp_admin_environment_scopes(g.user)
            user_id = request.form.get("user_id", "")
            if (
                actor_scopes is not None
                and not repository.customer_user_accessible_in_environments(
                    user_id, actor_scopes
                )
            ):
                abort(404)
            repository.assign_customer_membership(
                user_id,
                tenant_id,
                request.form.get("role", "CUSTOMER_VIEWER"),
            )
            flash("사용자와 고객사를 연결했습니다.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_users"))

    @app.post("/msp/schedules/<schedule_id>/enabled")
    @_msp_admin_required
    def set_schedule_enabled(schedule_id: str):
        scopes = _msp_admin_environment_scopes(g.user)
        if scopes is not None:
            environment = repository.schedule_environment(schedule_id)
            if environment not in scopes:
                abort(404)
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
            scopes = _msp_admin_environment_scopes(g.user)
            if scopes is not None:
                allowed_account_ids = {
                    str(item["id"])
                    for item in repository.schedulable_accounts(scopes)
                }
                if not account_ids or not set(account_ids).issubset(
                    allowed_account_ids
                ):
                    abort(403)
            report_type = request.form.get("report_type", "DAILY")
            if action == "delete":
                count = jobs.bulk_delete_schedules(account_ids, report_type)
                flash(f"선택한 일정 {count}개를 삭제했습니다.", "success")
            elif action == "create":
                try:
                    run_hour = int(request.form.get("run_hour", "9"))
                    run_minute = int(request.form.get("run_minute", "0"))
                    monthly_day_text = request.form.get(
                        "monthly_day", ""
                    ).strip()
                    weekly_day_text = request.form.get(
                        "weekly_day", ""
                    ).strip()
                    monthly_day = (
                        int(monthly_day_text) if monthly_day_text else None
                    )
                    weekly_day = (
                        int(weekly_day_text) if weekly_day_text else None
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "실행 시각 또는 실행 요일·날짜가 올바르지 않습니다."
                    ) from exc
                count = jobs.bulk_upsert_schedules(
                    account_ids,
                    report_type,
                    run_hour,
                    run_minute,
                    monthly_day,
                    str(g.user["id"]),
                    weekly_day=weekly_day,
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
        if environment not in {"public", "gov"}:
            abort(404)
        admin_scopes = _msp_admin_environment_scopes(g.user)
        if admin_scopes is not None and environment not in admin_scopes:
            abort(404)
        try:
            tenant_id = repository.create_tenant(
                request.form.get("customer_code", ""),
                request.form.get("customer_name", ""),
                environment,
                request.form.get(
                    "region",
                    "KRS" if environment == "gov" else "KR",
                ),
            )
            flash("고객사를 등록했습니다.", "success")
            return redirect(url_for("msp_customer", tenant_id=tenant_id))
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("msp_customers", environment=environment))

    @app.get("/msp/customer/<tenant_id>")
    @_msp_required
    def msp_customer(tenant_id: str):
        tenant = tenant_for_request(tenant_id)
        tenant.setdefault("report_options", default_report_options())
        return render_template(
            "customer_detail.html",
            tenant=tenant,
            tenant_users=(
                repository.users_for_tenant(tenant_id)
                if _can_manage_tenant(
                    g.user, tenant_id, tenant["environment"]
                )
                else []
            ),
            reports=tenant["reports"][:CUSTOMER_DETAIL_RECENT_LIMIT],
            jobs=repository.jobs_for_tenants([tenant_id])[
                :CUSTOMER_DETAIL_RECENT_LIMIT
            ],
            recent_item_limit=CUSTOMER_DETAIL_RECENT_LIMIT,
            can_manage_schedules=_can_manage_tenant(
                g.user, tenant_id, tenant["environment"]
            ),
            can_delete_reports=True,
            report_section_options=tenant["report_options"]["section_order"],
            report_section_labels=REPORT_SECTION_LABELS,
            report_section_descriptions=REPORT_SECTION_DESCRIPTIONS,
            resource_category_options=RESOURCE_CATEGORY_OPTIONS,
            resource_category_labels=RESOURCE_CATEGORY_LABELS,
            monitoring_category_options=MONITORING_CATEGORY_OPTIONS,
        )

    @app.post("/msp/customer/<tenant_id>/report-settings")
    @_msp_admin_required
    def update_customer_report_settings(tenant_id: str):
        tenant_for_request(tenant_id, manage=True)
        try:
            repository.update_tenant_report_settings(
                tenant_id,
                {
                    "sections": request.form.getlist("sections"),
                    "section_order": request.form.getlist("section_order"),
                    "resource_categories": request.form.getlist(
                        "resource_categories"
                    ),
                    "monitoring_categories": request.form.getlist(
                        "monitoring_categories"
                    ),
                    "operational_analysis": {
                        "enabled": request.form.get(
                            "analysis_enabled"
                        ) == "true",
                        "collect_wms": request.form.get(
                            "collect_wms"
                        ) == "true",
                        "collect_security_monitoring": request.form.get(
                            "collect_security_monitoring"
                        ) == "true",
                        "thresholds": {
                            name: request.form.get(name)
                            for name in (
                                "cpu_warning_percent",
                                "cpu_critical_percent",
                                "memory_warning_percent",
                                "memory_critical_percent",
                                "disk_warning_percent",
                                "disk_critical_percent",
                                "sustained_minutes",
                                "cost_increase_warning_percent",
                                "availability_warning_percent",
                                "availability_critical_percent",
                                "response_time_warning_ms",
                            )
                        },
                    },
                },
                str(g.user["id"]),
                retention_policies=retention_policies_from_form(),
            )
            flash("고객별 보고서 출력·보존 설정을 저장했습니다.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_customer", tenant_id=tenant_id))

    @app.post("/msp/customer/<tenant_id>/logo")
    @_msp_admin_required
    def update_customer_logo(tenant_id: str):
        tenant_for_request(tenant_id, manage=True)
        try:
            upload = request.files.get("logo")
            logo_url = request.form.get("logo_url", "").strip()
            has_upload = upload is not None and bool(upload.filename)
            if has_upload and logo_url:
                raise ValueError("로고 파일과 URL 중 한 가지만 입력하세요.")
            if logo_url:
                logo = fetch_customer_logo_from_url(logo_url)
            elif has_upload and upload is not None:
                content = upload.stream.read(MAX_CUSTOMER_LOGO_BYTES + 1)
                logo = validate_customer_logo(content, upload.mimetype)
            else:
                raise ValueError("등록할 고객사 로고 파일 또는 HTTPS URL을 입력하세요.")
            repository.update_tenant_logo(
                tenant_id,
                logo,
                str(g.user["id"]),
            )
            flash(
                "고객사 로고를 저장했습니다. 새로 생성하는 보고서부터 적용됩니다.",
                "success",
            )
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_customer", tenant_id=tenant_id))

    @app.post("/msp/customer/<tenant_id>/logo/delete")
    @_msp_admin_required
    def delete_customer_logo(tenant_id: str):
        tenant_for_request(tenant_id, manage=True)
        try:
            repository.delete_tenant_logo(tenant_id, str(g.user["id"]))
            flash(
                "고객사 로고를 삭제했습니다. 기존 보고서의 로고는 유지됩니다.",
                "success",
            )
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_customer", tenant_id=tenant_id))

    @app.post("/msp/customer/<tenant_id>/credentials")
    @_msp_admin_required
    def register_credential(tenant_id: str):
        tenant_for_request(tenant_id, manage=True)
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
        tenant_for_request(tenant_id, manage=True)
        try:
            tenant = repository.tenant_detail(tenant_id)
            account = next(
                (
                    item
                    for item in (tenant or {}).get("accounts", [])
                    if str(item["id"]) == account_id
                ),
                None,
            )
            confirmation = request.form.get("confirm_account_code", "").strip()
            if not account or confirmation != account["account_code"]:
                raise ValueError("삭제 확인을 위해 계정 코드를 정확히 입력하세요.")
            account_name = repository.delete_account_credential(
                tenant_id,
                account_id,
                str(g.user["id"]),
            )
            flash(
                f"{account_name}의 API 키를 삭제하고 계정을 중지했습니다.",
                "success",
            )
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_customer", tenant_id=tenant_id))

    @app.post("/msp/customer/<tenant_id>/delete")
    @_msp_admin_required
    def delete_customer(tenant_id: str):
        tenant_for_request(tenant_id, manage=True)
        try:
            tenant = repository.tenant_detail(tenant_id)
            confirmation = request.form.get("confirm_customer_code", "").strip()
            if not tenant or confirmation != tenant["customer_code"]:
                raise ValueError("삭제 확인을 위해 고객 코드를 정확히 입력하세요.")
            customer_name = repository.offboard_tenant(
                tenant_id,
                str(g.user["id"]),
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
        tenant_for_request(tenant_id, manage=True)
        try:
            tenant = repository.tenant_detail(tenant_id)
            confirmation = request.form.get("confirm_customer_code", "").strip()
            if not tenant or confirmation != tenant["customer_code"]:
                raise ValueError(
                    "재활성화 확인을 위해 고객 코드를 정확히 입력하세요."
                )
            customer_name = repository.reactivate_tenant(
                tenant_id,
                str(g.user["id"]),
            )
            flash(
                f"{customer_name} 고객을 재활성화했습니다. "
                "API 키와 사용자 권한을 다시 등록하세요.",
                "success",
            )
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_customer", tenant_id=tenant_id))

    @app.post("/msp/customer/<tenant_id>/anonymize")
    @_msp_admin_required
    def anonymize_customer(tenant_id: str):
        tenant_for_request(tenant_id, manage=True)
        try:
            tenant = repository.tenant_detail(tenant_id)
            code = request.form.get("confirm_customer_code", "").strip()
            phrase = request.form.get("confirm_phrase", "").strip()
            if not tenant or code != tenant["customer_code"] or phrase != "익명화":
                raise ValueError(
                    "고객 코드와 확인 문구 '익명화'를 정확히 입력하세요."
                )
            anonymous_name = repository.anonymize_tenant(
                tenant_id,
                str(g.user["id"]),
            )
            flash(
                f"고객 개인정보를 {anonymous_name}(으)로 익명화했습니다. "
                "이 작업은 되돌릴 수 없습니다.",
                "success",
            )
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_customer", tenant_id=tenant_id))

    @app.post("/msp/customer/<tenant_id>/permanent-delete")
    @_msp_admin_required
    def permanently_delete_customer(tenant_id: str):
        tenant = tenant_for_request(tenant_id, manage=True)
        try:
            code = request.form.get("confirm_customer_code", "").strip()
            phrase = request.form.get("confirm_phrase", "").strip()
            if code != tenant["customer_code"] or phrase != "영구 삭제":
                raise ValueError(
                    "고객 코드와 확인 문구 '영구 삭제'를 정확히 입력하세요."
                )
            customer_name, report_count = repository.permanently_delete_tenant(
                tenant_id,
                str(g.user["id"]),
                request.form.get("archive_reference", ""),
            )
            flash(
                f"{customer_name} 고객을 영구 삭제했습니다. "
                f"삭제된 보고서 {report_count}건의 원장은 보존됩니다. "
                "로컬 산출물 정리는 재시도 큐에서 처리됩니다.",
                "success",
            )
            return redirect(
                url_for("msp_customers", environment=tenant["environment"])
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("msp_customer", tenant_id=tenant_id))
