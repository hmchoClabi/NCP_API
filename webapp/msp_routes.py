"""MSP 운영자용 고객·사용자·일정 관리 라우트를 등록한다."""

from __future__ import annotations

from typing import Any

from flask import Flask, abort, flash, g, redirect, render_template, request, url_for

from app.report_branding import MAX_CUSTOMER_LOGO_BYTES, validate_customer_logo
from app.report_options import (
    DIAGRAM_BOOLEAN_OPTIONS,
    DIAGRAM_OPTION_LABELS,
    MONITORING_CATEGORY_OPTIONS,
    REPORT_SECTION_LABELS,
    REPORT_SECTION_OPTIONS,
    RESOURCE_CATEGORY_LABELS,
    RESOURCE_CATEGORY_OPTIONS,
    default_report_options,
)
from webapp.route_access import _can_manage_tenant, _msp_admin_required, _msp_required
from webapp.security import CredentialCipher, LocalKeyEncryptionProvider


def register_msp_routes(app: Flask, repository: Any, jobs: Any) -> None:
    """MSP 역할 경계가 필요한 관리 라우트를 기존 endpoint로 등록한다."""

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
                    raise ValueError(
                        "실행 시각 또는 월간 실행일이 올바르지 않습니다."
                    ) from exc
                count = jobs.bulk_upsert_schedules(
                    account_ids,
                    report_type,
                    run_hour,
                    run_minute,
                    monthly_day,
                    str(g.user["id"]),
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
        tenant = repository.tenant_detail(tenant_id)
        if not tenant:
            abort(404)
        tenant.setdefault("report_options", default_report_options())
        return render_template(
            "customer_detail.html",
            tenant=tenant,
            tenant_users=(
                repository.users_for_tenant(tenant_id)
                if "MSP_ADMIN" in set(g.user.get("platform_roles", []))
                else []
            ),
            reports=tenant["reports"],
            jobs=repository.jobs_for_tenants([tenant_id]),
            can_manage_schedules=_can_manage_tenant(g.user, tenant_id),
            can_delete_reports=True,
            report_section_options=REPORT_SECTION_OPTIONS,
            report_section_labels=REPORT_SECTION_LABELS,
            resource_category_options=RESOURCE_CATEGORY_OPTIONS,
            resource_category_labels=RESOURCE_CATEGORY_LABELS,
            monitoring_category_options=MONITORING_CATEGORY_OPTIONS,
            diagram_boolean_options=DIAGRAM_BOOLEAN_OPTIONS,
            diagram_option_labels=DIAGRAM_OPTION_LABELS,
        )

    @app.post("/msp/customer/<tenant_id>/report-settings")
    @_msp_admin_required
    def update_customer_report_settings(tenant_id: str):
        try:
            diagram = {
                key: request.form.get(f"diagram_{key}") == "true"
                for key in DIAGRAM_BOOLEAN_OPTIONS
            }
            diagram["max_nodes"] = request.form.get("diagram_max_nodes", "120")
            repository.update_tenant_report_settings(
                tenant_id,
                {
                    "sections": request.form.getlist("sections"),
                    "resource_categories": request.form.getlist(
                        "resource_categories"
                    ),
                    "monitoring_categories": request.form.getlist(
                        "monitoring_categories"
                    ),
                    "diagram": diagram,
                },
                str(g.user["id"]),
            )
            flash("고객별 보고서 출력 설정을 저장했습니다.", "success")
        except ValueError as exc:
            flash(str(exc), "error")
        return redirect(url_for("msp_customer", tenant_id=tenant_id))

    @app.post("/msp/customer/<tenant_id>/logo")
    @_msp_admin_required
    def update_customer_logo(tenant_id: str):
        try:
            upload = request.files.get("logo")
            if upload is None or not upload.filename:
                raise ValueError("등록할 고객사 로고 파일을 선택하세요.")
            content = upload.stream.read(MAX_CUSTOMER_LOGO_BYTES + 1)
            logo = validate_customer_logo(content, upload.mimetype)
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
