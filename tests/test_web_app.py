import base64
import io
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.report_branding import validate_customer_logo
from webapp.app import CSRF_COOKIE, SESSION_COOKIE, create_app
from webapp.route_access import (
    _can_access_tenant,
    _can_manage_tenant,
    _msp_environment_scopes,
)
from webapp.security import token_hash


class FakePortalRepository:
    def __init__(self):
        self.allowed_tenants = None
        self.created_portal_users = []
        self.assigned_memberships = []
        self.deleted_credentials = []
        self.offboarded_tenants = []
        self.reactivated_tenants = []
        self.anonymized_tenants = []
        self.permanently_deleted_tenants = []
        self.deleted_reports = []
        self.created_msp_users = []
        self.updated_msp_users = []
        self.msp_status_error = None
        self.updated_report_settings = []
        self.updated_logos = []
        self.deleted_logos = []

    def session_user(self, session_token):
        if not session_token:
            return None
        return {
            "id": "user-1",
            "email": "viewer@example.com",
            "display_name": "Viewer",
            "platform_roles": [],
            "memberships": [{"tenant_id": "tenant-1", "customer_name": "Customer"}],
            "csrf_token_hash": token_hash("csrf-token"),
        }

    def report_detail(self, report_id, allowed_tenants):
        self.allowed_tenants = allowed_tenants
        tenant_id = "tenant-gov" if report_id == "report-gov" else "tenant-1"
        if allowed_tenants is not None and tenant_id not in allowed_tenants:
            return None
        return {
            "id": report_id,
            "tenant_id": tenant_id,
            "customer_name": "Customer",
            "report_type": "DAILY",
            "period_start": datetime(2026, 8, 1),
            "period_end": datetime(2026, 8, 2),
            "account_name": "Primary",
            "status": "SUCCESS",
            "error_count": 0,
            "snapshot": {
                "period": {
                    "period_type": "day",
                    "start_dt": "2026-08-01 00:00:00",
                    "end_dt": "2026-08-01 23:59:59",
                    "file_suffix": "20260801_20260801",
                },
                "customer": {"name": "Customer"},
                "servers": [{"server_name": "web-1"}],
            },
        }

    def account_tenant(self, account_id):
        return "tenant-1" if account_id == "account-1" else None

    def update_tenant_report_settings(self, tenant_id, options, actor_id):
        self.updated_report_settings.append((tenant_id, options, actor_id))
        return options

    def update_tenant_logo(self, tenant_id, logo, actor_id):
        self.updated_logos.append((tenant_id, logo, actor_id))

    def delete_tenant_logo(self, tenant_id, actor_id):
        self.deleted_logos.append((tenant_id, actor_id))

    def tenant_detail(self, tenant_id):
        if tenant_id != "tenant-1":
            return None
        return {
            "id": tenant_id,
            "customer_name": "Customer",
            "customer_code": "customer",
            "region": "KR",
            "environment": "public",
            "status": "ACTIVE",
            "metadata": {},
            "branding": {},
            "accounts": [{
                "id": "account-1",
                "account_code": "primary",
                "display_name": "Primary",
                "status": "ACTIVE",
                "credential_status": "VALID",
                "access_key_hint": "***-KEY",
                "credential_version": 1,
                "rotated_at": datetime(2026, 8, 4, 0, 0, tzinfo=timezone.utc),
                "schedules": [],
            }],
            "reports": [{
                "id": "report-1",
                "report_type": "DAILY",
                "period_start": datetime(2026, 8, 2),
                "period_end": datetime(2026, 8, 3),
                "account_name": "Primary",
                "status": "SUCCESS",
                "error_count": 0,
                "created_at": datetime(2026, 8, 3, 0, 5, tzinfo=timezone.utc),
                "completed_at": datetime(
                    2026, 8, 3, 0, 7, 5, tzinfo=timezone.utc
                ),
                "execution_seconds": 125,
            }],
        }

    def users_for_tenant(self, tenant_id):
        return [{
            "id": "customer-user-1",
            "email": "customer@example.com",
            "display_name": "Customer User",
            "user_status": "ACTIVE",
            "role": "CUSTOMER_VIEWER",
            "membership_status": "ACTIVE",
        }]

    def customer_users(self, allowed_environments=None):
        return [{
            "id": "customer-user-1",
            "email": "customer@example.com",
            "display_name": "Customer User",
            "user_status": "ACTIVE",
            "last_login_at": None,
            "created_at": datetime(2026, 8, 1),
            "memberships": [{
                "tenant_id": "tenant-1",
                "customer_name": "Customer",
                "environment": "public",
                "role": "CUSTOMER_VIEWER",
                "status": "ACTIVE",
            }],
        }]

    def create_portal_user(self, email, password, display_name):
        self.created_portal_users.append((email, password, display_name))
        return "customer-user-1"

    def create_msp_user(
        self, email, password, display_name, role, environment_scope=None,
        actor_id=None,
    ):
        self.created_msp_users.append(
            (email, password, display_name, role, environment_scope, actor_id)
        )
        return "msp-user-2"

    def set_msp_user_enabled(self, user_id, actor_id, enabled):
        if self.msp_status_error:
            raise ValueError(self.msp_status_error)
        self.updated_msp_users.append((user_id, actor_id, enabled))
        return "MSP Operator"

    def msp_users(self, allowed_environments=None):
        return [{
            "id": "msp-user-1",
            "email": "admin@example.com",
            "display_name": "MSP Admin",
            "user_status": "ACTIVE",
            "role": "MSP_ADMIN",
            "environment_scope": None,
            "last_login_at": None,
            "created_at": datetime(2026, 8, 1),
        }]

    def assign_customer_membership(self, user_id, tenant_id, role):
        self.assigned_memberships.append((user_id, tenant_id, role))

    def customer_user_accessible_in_environments(
        self, user_id, allowed_environments
    ):
        return user_id == "customer-user-1" and "public" in allowed_environments

    def jobs_for_tenants(self, tenant_ids):
        return []

    def notification_events(self, tenant_ids, after):
        self.notification_tenants = tenant_ids
        return [{
            "id": "job-1",
            "status": "SUCCESS",
            "occurred_at": datetime(2026, 8, 4, 1, 0, tzinfo=timezone.utc),
            "report_type": "DAILY",
            "customer_name": "Customer",
            "account_name": "Primary",
        }]

    def delete_account_credential(self, tenant_id, account_id, actor_id):
        self.deleted_credentials.append((tenant_id, account_id, actor_id))
        return "Primary"

    def offboard_tenant(self, tenant_id, actor_id):
        self.offboarded_tenants.append((tenant_id, actor_id))
        return "Customer"

    def reactivate_tenant(self, tenant_id, actor_id):
        self.reactivated_tenants.append((tenant_id, actor_id))
        return "Customer"

    def anonymize_tenant(self, tenant_id, actor_id):
        self.anonymized_tenants.append((tenant_id, actor_id))
        return "익명 고객 12345678"

    def permanently_delete_tenant(
        self, tenant_id, actor_id, archive_reference="", *, force=False,
    ):
        self.permanently_deleted_tenants.append(
            (tenant_id, actor_id, archive_reference, force)
        )
        return "Customer", 1

    def delete_report(self, report_id, actor_id):
        self.deleted_reports.append((report_id, actor_id))
        return {
            "tenant_id": "tenant-1",
            "customer_name": "Customer",
            "removed_artifact_files": 1,
            "failed_artifact_files": 0,
        }

    def schedule_environment(self, schedule_id):
        return "public" if schedule_id == "schedule-1" else None

    def msp_user_environment_scopes(self, user_id):
        return {"public"}

    def schedules(self, allowed_environments=None):
        return []

    def schedulable_accounts(self, allowed_environments=None):
        return [{
            "id": "11111111-1111-1111-1111-111111111111",
            "tenant_id": "tenant-1",
            "account_code": "primary",
            "account_name": "Primary",
            "customer_code": "customer",
            "customer_name": "Customer",
            "environment": "public",
        }]

    def tenants(self, environment=None, allowed_environments=None):
        return [{
            "id": "tenant-1",
            "customer_code": "customer",
            "customer_name": "Customer",
            "environment": "public",
            "region": "KR",
            "status": "ACTIVE",
            "account_count": 1,
            "report_count": 1,
        }]

    def tenant_ids_for_environments(self, allowed_environments):
        return ["tenant-1"] if "public" in allowed_environments else []

    def dashboard(self, allowed_environments=None):
        return {
            "summary": {
                "customer_count": 1,
                "public_count": 1,
                "gov_count": 0,
                "issue_count": 0,
            },
            "issue_customers": [],
        }

    def accounts_for_tenants(self, tenant_ids):
        return []

    def reports_for_tenants(self, tenant_ids):
        return []

    def report_history(self, tenant_ids=None):
        self.history_tenants = tenant_ids
        return []


class FakeReportJobRepository:
    def __init__(self):
        self.enqueued = []
        self.bulk_upserts = []
        self.bulk_deletes = []

    def enqueue(
        self, account_id, report_type, target_value, requested_by,
        start_datetime=None, end_datetime=None,
    ):
        self.enqueued.append((
            account_id, report_type, target_value, requested_by,
            start_datetime, end_datetime,
        ))
        return "job-1"

    def set_schedule_enabled(self, schedule_id, enabled):
        return schedule_id == "schedule-1"

    def bulk_upsert_schedules(
        self, account_ids, report_type, run_hour, run_minute,
        monthly_day, actor_id,
    ):
        self.bulk_upserts.append((
            account_ids, report_type, run_hour, run_minute,
            monthly_day, actor_id,
        ))
        return len(account_ids)

    def bulk_delete_schedules(self, account_ids, report_type):
        self.bulk_deletes.append((account_ids, report_type))
        return len(account_ids)


class MspEnvironmentScopeTests(unittest.TestCase):
    def test_scoped_msp_can_only_access_matching_environment(self):
        user = {
            "platform_roles": ["MSP_OPERATOR"],
            "platform_role_bindings": [{
                "role": "MSP_OPERATOR",
                "environment_scope": "public",
            }],
            "memberships": [],
        }

        self.assertEqual(_msp_environment_scopes(user), {"public"})
        self.assertTrue(_can_access_tenant(user, "tenant-1", "public"))
        self.assertFalse(_can_access_tenant(user, "tenant-2", "gov"))
        self.assertFalse(_can_access_tenant(user, "tenant-1"))

    def test_admin_scope_is_not_widened_by_operator_scope(self):
        user = {
            "platform_roles": ["MSP_ADMIN", "MSP_OPERATOR"],
            "platform_role_bindings": [
                {"role": "MSP_ADMIN", "environment_scope": "public"},
                {"role": "MSP_OPERATOR", "environment_scope": "gov"},
            ],
            "memberships": [],
        }

        self.assertEqual(_msp_environment_scopes(user), {"public", "gov"})
        self.assertTrue(_can_manage_tenant(user, "tenant-1", "public"))
        self.assertFalse(_can_manage_tenant(user, "tenant-2", "gov"))

    def test_legacy_unscoped_msp_context_remains_global(self):
        user = {"platform_roles": ["MSP_ADMIN"], "memberships": []}

        self.assertIsNone(_msp_environment_scopes(user))
        self.assertTrue(_can_access_tenant(user, "tenant-1", "public"))
        self.assertTrue(_can_manage_tenant(user, "tenant-2", "gov"))


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.repository = FakePortalRepository()
        self.jobs = FakeReportJobRepository()
        self.app = create_app(
            {
                "TESTING": True,
                "PORTAL_REPOSITORY": self.repository,
                "REPORT_JOB_REPOSITORY": self.jobs,
                "APP_VERSION": "build-5",
                "APP_SOURCE_REVISION": "1234567890abcdef",
            }
        )
        self.client = self.app.test_client()

    def test_login_form_sets_and_submits_csrf_token(self):
        response = self.client.get("/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="csrf_token"', response.data)
        self.assertIn(CSRF_COOKIE, response.headers.get("Set-Cookie", ""))
        self.assertIn("버전 build-5 · 1234567".encode("utf-8"), response.data)

        rejected = self.app.test_client().post(
            "/login",
            data={"email": "viewer@example.com", "password": "invalid"},
        )
        self.assertEqual(rejected.status_code, 403)

    def test_all_portal_templates_compile(self):
        for template_name in self.app.jinja_env.list_templates():
            self.app.jinja_env.get_template(template_name)

    def test_route_contract_preserves_endpoint_rules_and_methods(self):
        routes = {
            rule.endpoint: (
                rule.rule,
                tuple(sorted(rule.methods - {"HEAD", "OPTIONS"})),
            )
            for rule in self.app.url_map.iter_rules()
            if rule.endpoint != "static"
        }

        self.assertEqual(
            routes,
            {
                "health_live": ("/health/live", ("GET",)),
                "health_ready": ("/health/ready", ("GET",)),
                "login": ("/login", ("GET", "POST")),
                "logout": ("/logout", ("POST",)),
                "index": ("/", ("GET",)),
                "msp_dashboard": ("/msp", ("GET",)),
                "msp_customers": ("/msp/customers/<environment>", ("GET",)),
                "msp_schedules": ("/msp/schedules", ("GET",)),
                "msp_users": ("/msp/users", ("GET",)),
                "create_portal_user": ("/msp/users", ("POST",)),
                "create_msp_user": ("/msp/users/platform", ("POST",)),
                "set_msp_user_enabled": (
                    "/msp/users/platform/<user_id>/enabled",
                    ("POST",),
                ),
                "assign_portal_user": ("/msp/users/memberships", ("POST",)),
                "set_schedule_enabled": (
                    "/msp/schedules/<schedule_id>/enabled",
                    ("POST",),
                ),
                "bulk_schedules": ("/msp/schedules/bulk", ("POST",)),
                "create_customer": ("/msp/customers/<environment>", ("POST",)),
                "msp_customer": ("/msp/customer/<tenant_id>", ("GET",)),
                "update_customer_report_settings": (
                    "/msp/customer/<tenant_id>/report-settings",
                    ("POST",),
                ),
                "update_customer_logo": (
                    "/msp/customer/<tenant_id>/logo",
                    ("POST",),
                ),
                "delete_customer_logo": (
                    "/msp/customer/<tenant_id>/logo/delete",
                    ("POST",),
                ),
                "register_credential": (
                    "/msp/customer/<tenant_id>/credentials",
                    ("POST",),
                ),
                "delete_credential": (
                    "/msp/customer/<tenant_id>/credentials/<account_id>/delete",
                    ("POST",),
                ),
                "delete_customer": (
                    "/msp/customer/<tenant_id>/delete",
                    ("POST",),
                ),
                "reactivate_customer": (
                    "/msp/customer/<tenant_id>/reactivate",
                    ("POST",),
                ),
                "anonymize_customer": (
                    "/msp/customer/<tenant_id>/anonymize",
                    ("POST",),
                ),
                "permanently_delete_customer": (
                    "/msp/customer/<tenant_id>/permanent-delete",
                    ("POST",),
                ),
                "enqueue_report": (
                    "/accounts/<account_id>/report-jobs",
                    ("POST",),
                ),
                "save_schedule": (
                    "/accounts/<account_id>/schedules",
                    ("POST",),
                ),
                "customer_portal": ("/portal", ("GET",)),
                "report_detail": ("/reports/<report_id>", ("GET",)),
                "delete_report": ("/reports/<report_id>/delete", ("POST",)),
                "report_history": ("/history", ("GET",)),
                "notifications": ("/notifications", ("GET",)),
                "report_content": ("/reports/<report_id>/content", ("GET",)),
            },
        )

    def test_customer_report_lookup_is_scoped_to_membership(self):
        self.client.set_cookie(SESSION_COOKIE, "session-token")
        response = self.client.get("/reports/report-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.repository.allowed_tenants, ["tenant-1"])
        self.assertIn(
            (
                "<span>자원</span><strong>1</strong>"
                "<small>수집 대상</small>"
            ).encode("utf-8"),
            response.data,
        )

    def test_customer_can_render_full_report_from_stored_snapshot(self):
        self.client.set_cookie(SESSION_COOKIE, "session-token")
        response = self.client.get("/reports/report-1/content")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.content_type)
        self.assertIn("서버 메트릭".encode("utf-8"), response.data)
        self.assertIn(b"web-1", response.data)
        self.assertIn("frame-ancestors 'self'", response.headers["Content-Security-Policy"])

    def test_customer_viewer_can_enqueue_own_account_report(self):
        self.client.set_cookie(SESSION_COOKIE, "session-token")
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        response = self.client.post(
            "/accounts/account-1/report-jobs",
            data={
                "csrf_token": "csrf-token",
                "report_type": "DAILY",
                "target_value": "2026-08-02",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.jobs.enqueued,
            [("account-1", "DAILY", "2026-08-02", "user-1", None, None)],
        )

    def test_customer_can_enqueue_custom_time_range(self):
        self.client.set_cookie(SESSION_COOKIE, "session-token")
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        response = self.client.post(
            "/accounts/account-1/report-jobs",
            data={
                "csrf_token": "csrf-token",
                "report_type": "CUSTOM",
                "start_datetime": "2026-08-03T08:00",
                "end_datetime": "2026-08-03T09:00",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.jobs.enqueued[0][1], "CUSTOM")
        self.assertEqual(self.jobs.enqueued[0][4:], (
            "2026-08-03T08:00", "2026-08-03T09:00"
        ))

    def test_customer_viewer_cannot_change_schedule(self):
        self.client.set_cookie(SESSION_COOKIE, "session-token")
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        response = self.client.post(
            "/accounts/account-1/schedules",
            data={"csrf_token": "csrf-token", "report_type": "DAILY"},
        )

        self.assertEqual(response.status_code, 403)

    def test_customer_viewer_cannot_open_user_management(self):
        self.client.set_cookie(SESSION_COOKIE, "session-token")
        response = self.client.get("/msp/users")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.repository.created_portal_users, [])

    def test_customer_viewer_cannot_create_msp_user_or_bulk_schedule(self):
        self.client.set_cookie(SESSION_COOKIE, "session-token")
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")

        msp_response = self.client.post(
            "/msp/users/platform",
            data={"csrf_token": "csrf-token"},
        )
        status_response = self.client.post(
            "/msp/users/platform/msp-user-1/enabled",
            data={"csrf_token": "csrf-token", "enabled": "false"},
        )
        schedule_response = self.client.post(
            "/msp/schedules/bulk",
            data={"csrf_token": "csrf-token"},
        )

        self.assertEqual(msp_response.status_code, 403)
        self.assertEqual(status_response.status_code, 403)
        self.assertEqual(schedule_response.status_code, 403)
        self.assertEqual(self.repository.created_msp_users, [])
        self.assertEqual(self.repository.updated_msp_users, [])
        self.assertEqual(self.jobs.bulk_upserts, [])

    def test_customer_viewer_cannot_delete_report(self):
        self.client.set_cookie(SESSION_COOKIE, "session-token")
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")

        response = self.client.post(
            "/reports/report-1/delete",
            data={"csrf_token": "csrf-token"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.repository.deleted_reports, [])

    def test_msp_operator_can_delete_report(self):
        original_session_user = self.repository.session_user

        def msp_operator(session_token):
            user = original_session_user(session_token)
            if user:
                user["platform_roles"] = ["MSP_OPERATOR"]
            return user

        self.repository.session_user = msp_operator
        self.client.set_cookie(SESSION_COOKIE, "session-token")
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")

        response = self.client.post(
            "/reports/report-1/delete",
            data={"csrf_token": "csrf-token"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.repository.deleted_reports,
            [("report-1", "user-1")],
        )

    def test_msp_operator_cannot_manage_msp_accounts(self):
        original_session_user = self.repository.session_user

        def msp_operator(session_token):
            user = original_session_user(session_token)
            if user:
                user["platform_roles"] = ["MSP_OPERATOR"]
            return user

        self.repository.session_user = msp_operator
        self.client.set_cookie(SESSION_COOKIE, "session-token")
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")

        listing = self.client.get("/msp/users")
        creation = self.client.post(
            "/msp/users/platform",
            data={"csrf_token": "csrf-token"},
        )
        status_change = self.client.post(
            "/msp/users/platform/msp-user-2/enabled",
            data={"csrf_token": "csrf-token", "enabled": "false"},
        )

        self.assertEqual(listing.status_code, 403)
        self.assertEqual(creation.status_code, 403)
        self.assertEqual(status_change.status_code, 403)
        self.assertEqual(self.repository.created_msp_users, [])
        self.assertEqual(self.repository.updated_msp_users, [])

    def test_customer_viewer_cannot_delete_credentials_or_customer(self):
        self.client.set_cookie(SESSION_COOKIE, "session-token")
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")

        credential_response = self.client.post(
            "/msp/customer/tenant-1/credentials/account-1/delete",
            data={"csrf_token": "csrf-token", "confirm_account_code": "primary"},
        )
        customer_response = self.client.post(
            "/msp/customer/tenant-1/delete",
            data={"csrf_token": "csrf-token", "confirm_customer_code": "customer"},
        )
        reactivate_response = self.client.post(
            "/msp/customer/tenant-1/reactivate",
            data={"csrf_token": "csrf-token", "confirm_customer_code": "customer"},
        )
        anonymize_response = self.client.post(
            "/msp/customer/tenant-1/anonymize",
            data={
                "csrf_token": "csrf-token",
                "confirm_customer_code": "customer",
                "confirm_phrase": "익명화",
            },
        )
        permanent_response = self.client.post(
            "/msp/customer/tenant-1/permanent-delete",
            data={
                "csrf_token": "csrf-token",
                "confirm_customer_code": "customer",
                "confirm_phrase": "영구 삭제",
            },
        )

        self.assertEqual(credential_response.status_code, 403)
        self.assertEqual(customer_response.status_code, 403)
        self.assertEqual(reactivate_response.status_code, 403)
        self.assertEqual(anonymize_response.status_code, 403)
        self.assertEqual(permanent_response.status_code, 403)
        self.assertEqual(self.repository.deleted_credentials, [])
        self.assertEqual(self.repository.offboarded_tenants, [])
        self.assertEqual(self.repository.reactivated_tenants, [])
        self.assertEqual(self.repository.anonymized_tenants, [])
        self.assertEqual(self.repository.permanently_deleted_tenants, [])

    def test_customer_history_is_scoped_to_membership(self):
        self.client.set_cookie(SESSION_COOKIE, "session-token")
        response = self.client.get("/history")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.repository.history_tenants, ["tenant-1"])

    def test_notification_feed_is_scoped_and_uses_kst(self):
        self.client.set_cookie(SESSION_COOKIE, "session-token")
        response = self.client.get(
            "/notifications?after=2026-08-04T00:00:00%2B00:00"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.repository.notification_tenants, ["tenant-1"])
        event = response.get_json()["events"][0]
        self.assertEqual(event["occurred_at_kst"], "2026-08-04 10:00:00 KST")

    def test_kst_template_filter_converts_utc(self):
        formatter = self.app.jinja_env.filters["kst"]

        self.assertEqual(
            formatter(datetime(2026, 8, 4, 0, 30, tzinfo=timezone.utc)),
            "2026-08-04 09:30:00 KST",
        )

    def test_duration_template_filter_formats_elapsed_seconds(self):
        formatter = self.app.jinja_env.filters["duration"]

        self.assertEqual(formatter(None), "-")
        self.assertEqual(formatter(0), "0초")
        self.assertEqual(formatter(125), "2분 5초")
        self.assertEqual(formatter(3_661), "1시간 1분 1초")

    def test_inclusive_end_filter_converts_exclusive_month_boundary(self):
        formatter = self.app.jinja_env.filters["inclusive_end"]

        converted = formatter(
            datetime(2026, 8, 1, tzinfo=timezone.utc), True
        )

        self.assertEqual(converted.date().isoformat(), "2026-07-31")


class MspCustomerDetailTests(unittest.TestCase):
    def setUp(self):
        self.repository = FakePortalRepository()
        original_session_user = self.repository.session_user

        def msp_user(session_token):
            user = original_session_user(session_token)
            if user:
                user["platform_roles"] = ["MSP_ADMIN"]
            return user

        self.repository.session_user = msp_user
        self.jobs = FakeReportJobRepository()
        self.app = create_app({
            "TESTING": True,
            "PORTAL_REPOSITORY": self.repository,
            "REPORT_JOB_REPOSITORY": self.jobs,
        })
        self.client = self.app.test_client()
        self.client.set_cookie(SESSION_COOKIE, "session-token")

    def use_scoped_msp(self, role: str, environment: str) -> None:
        def scoped_user(session_token):
            if not session_token:
                return None
            return {
                "id": "user-1",
                "email": "scoped@example.com",
                "display_name": "Scoped MSP",
                "platform_roles": [role],
                "platform_role_bindings": [{
                    "role": role,
                    "environment_scope": environment,
                }],
                "memberships": [],
                "csrf_token_hash": token_hash("csrf-token"),
            }

        self.repository.session_user = scoped_user

    def test_customer_detail_renders_persisted_reports(self):
        response = self.client.get("/msp/customer/tenant-1")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"report-1", response.data)
        self.assertIn(b"customer@example.com", response.data)
        self.assertIn("생성 시각".encode("utf-8"), response.data)
        self.assertIn("2026-08-03 09:05:00 KST".encode("utf-8"), response.data)
        self.assertIn("2분 5초".encode("utf-8"), response.data)
        self.assertIn("보고서 삭제".encode("utf-8"), response.data)
        self.assertIn("고객별 보고서 출력 설정".encode("utf-8"), response.data)
        self.assertNotIn(b'name="resource_categories" value="SECRET', response.data)

    def test_customer_detail_limits_recent_reports_and_jobs_to_ten(self):
        original_tenant_detail = self.repository.tenant_detail

        def tenant_detail(tenant_id):
            tenant = original_tenant_detail(tenant_id)
            tenant["reports"] = [
                {
                    "id": f"recent-report-{index:02d}",
                    "report_type": "DAILY",
                    "period_start": datetime(2026, 8, 12 - index),
                    "period_end": datetime(2026, 8, 13 - index),
                    "end_exclusive": True,
                    "account_name": "Primary",
                    "status": "SUCCESS",
                    "error_count": 0,
                    "created_at": datetime(
                        2026, 8, 12 - index, tzinfo=timezone.utc
                    ),
                    "completed_at": datetime(
                        2026, 8, 12 - index, 0, 1, tzinfo=timezone.utc
                    ),
                    "execution_seconds": 60,
                }
                for index in range(1, 12)
            ]
            return tenant

        self.repository.tenant_detail = tenant_detail
        self.repository.jobs_for_tenants = lambda tenant_ids: [
            {
                "id": f"recent-job-{index:02d}",
                "customer_name": "Customer",
                "account_name": "Primary",
                "report_type": "DAILY",
                "target_value": f"recent-job-{index:02d}",
                "trigger_type": "MANUAL",
                "status": "SUCCESS",
                "last_error": None,
                "requested_at": datetime(
                    2026, 8, 12 - index, tzinfo=timezone.utc
                ),
            }
            for index in range(1, 12)
        ]

        response = self.client.get("/msp/customer/tenant-1")
        response_text = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        for index in range(1, 11):
            self.assertIn(f"recent-report-{index:02d}", response_text)
        self.assertNotIn("recent-report-11", response_text)
        for index in range(1, 11):
            self.assertIn(f"recent-job-{index:02d}", response_text)
        self.assertNotIn("recent-job-11", response_text)
        self.assertIn("최신 10건".encode("utf-8"), response.data)

    def test_msp_admin_can_update_customer_report_settings(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")

        response = self.client.post(
            "/msp/customer/tenant-1/report-settings",
            data={
                "csrf_token": "csrf-token",
                "sections": ["billing", "infrastructure_inventory"],
                "resource_categories": ["SERVER", "VPC"],
                "monitoring_categories": ["SERVER"],
            },
        )

        self.assertEqual(response.status_code, 302)
        tenant_id, options, actor_id = self.repository.updated_report_settings[0]
        self.assertEqual((tenant_id, actor_id), ("tenant-1", "user-1"))
        self.assertEqual(options["sections"], [
            "billing", "infrastructure_inventory",
        ])
        self.assertEqual(options["resource_categories"], ["SERVER", "VPC"])
        self.assertEqual(options["monitoring_categories"], ["SERVER"])

    def test_customer_detail_omits_action_cases_and_policy_exceptions(self):
        detail = self.client.get("/msp/customer/tenant-1")
        detail_text = detail.get_data(as_text=True)

        self.assertEqual(detail.status_code, 200)
        self.assertNotIn("운영 조치사항", detail_text)
        self.assertNotIn("정책 예외 승인", detail_text)
        self.assertNotIn("/action-cases/", detail_text)
        self.assertNotIn("/policy-exceptions", detail_text)

    def test_removed_operational_management_routes_return_not_found(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        paths = (
            "/msp/customer/tenant-1/action-cases/case-1",
            "/msp/customer/tenant-1/policy-exceptions",
            "/msp/customer/tenant-1/policy-exceptions/exception-1/deactivate",
        )

        for path in paths:
            with self.subTest(path=path):
                response = self.client.post(
                    path,
                    data={"csrf_token": "csrf-token"},
                )
                self.assertEqual(response.status_code, 404)

    def test_msp_admin_can_upload_valid_customer_logo(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
            "AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )

        response = self.client.post(
            "/msp/customer/tenant-1/logo",
            data={
                "csrf_token": "csrf-token",
                "logo": (io.BytesIO(png), "customer.png", "image/png"),
            },
        )

        self.assertEqual(response.status_code, 302)
        tenant_id, logo, actor_id = self.repository.updated_logos[0]
        self.assertEqual((tenant_id, actor_id), ("tenant-1", "user-1"))
        self.assertEqual(logo.content_type, "image/png")
        self.assertEqual((logo.width, logo.height), (1, 1))
        self.assertTrue(logo.data_uri.startswith("data:image/png;base64,"))

    def test_msp_admin_can_import_customer_logo_from_https_url(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
            "AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        fetched_logo = validate_customer_logo(png, "image/png")

        with patch(
            "webapp.msp_routes.fetch_customer_logo_from_url",
            return_value=fetched_logo,
        ) as fetch_logo:
            response = self.client.post(
                "/msp/customer/tenant-1/logo",
                data={
                    "csrf_token": "csrf-token",
                    "logo_url": "https://assets.example.com/customer.png",
                },
            )

        self.assertEqual(response.status_code, 302)
        fetch_logo.assert_called_once_with(
            "https://assets.example.com/customer.png"
        )
        self.assertEqual(
            self.repository.updated_logos[0],
            ("tenant-1", fetched_logo, "user-1"),
        )

    def test_customer_logo_file_and_url_cannot_be_submitted_together(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")

        response = self.client.post(
            "/msp/customer/tenant-1/logo",
            data={
                "csrf_token": "csrf-token",
                "logo_url": "https://assets.example.com/customer.png",
                "logo": (io.BytesIO(b"not-used"), "customer.png", "image/png"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.repository.updated_logos, [])

    def test_svg_customer_logo_is_rejected(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")

        response = self.client.post(
            "/msp/customer/tenant-1/logo",
            data={
                "csrf_token": "csrf-token",
                "logo": (
                    io.BytesIO(b"<svg><script>alert(1)</script></svg>"),
                    "customer.png",
                    "image/png",
                ),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.repository.updated_logos, [])

    def test_msp_admin_can_delete_customer_logo(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")

        response = self.client.post(
            "/msp/customer/tenant-1/logo/delete",
            data={"csrf_token": "csrf-token"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.repository.deleted_logos,
            [("tenant-1", "user-1")],
        )

    def test_customer_viewer_cannot_update_report_settings(self):
        original_session_user = self.repository.session_user

        def customer_viewer(session_token):
            user = original_session_user(session_token)
            if user:
                user["platform_roles"] = []
            return user

        self.repository.session_user = customer_viewer
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")

        response = self.client.post(
            "/msp/customer/tenant-1/report-settings",
            data={"csrf_token": "csrf-token", "sections": "billing"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.repository.updated_report_settings, [])

    def test_customer_viewer_cannot_manage_customer_logo(self):
        original_session_user = self.repository.session_user

        def customer_viewer(session_token):
            user = original_session_user(session_token)
            if user:
                user["platform_roles"] = []
            return user

        self.repository.session_user = customer_viewer
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")

        upload = self.client.post(
            "/msp/customer/tenant-1/logo",
            data={"csrf_token": "csrf-token"},
        )
        delete = self.client.post(
            "/msp/customer/tenant-1/logo/delete",
            data={"csrf_token": "csrf-token"},
        )

        self.assertEqual(upload.status_code, 403)
        self.assertEqual(delete.status_code, 403)
        self.assertEqual(self.repository.updated_logos, [])
        self.assertEqual(self.repository.deleted_logos, [])

    def test_msp_account_can_delete_report(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")

        response = self.client.post(
            "/reports/report-1/delete",
            data={"csrf_token": "csrf-token"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.repository.deleted_reports,
            [("report-1", "user-1")],
        )

    def test_msp_admin_can_open_user_management(self):
        response = self.client.get("/msp/users")

        self.assertEqual(response.status_code, 200)
        self.assertIn("MSP 계정·사용자 관리".encode("utf-8"), response.data)
        self.assertIn("신규 MSP 계정".encode("utf-8"), response.data)
        self.assertIn(b"customer@example.com", response.data)

    def test_msp_admin_can_register_portal_user(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        response = self.client.post(
            "/msp/users",
            data={
                "csrf_token": "csrf-token",
                "email": "new-user@example.com",
                "display_name": "New User",
                "password": "temporary-password",
                "password_confirmation": "temporary-password",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.repository.created_portal_users, [(
            "new-user@example.com", "temporary-password", "New User",
        )])

    def test_msp_admin_can_register_another_msp_user(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        response = self.client.post(
            "/msp/users/platform",
            data={
                "csrf_token": "csrf-token",
                "email": "operator@example.com",
                "display_name": "Operator",
                "role": "MSP_OPERATOR",
                "password": "temporary-password",
                "password_confirmation": "temporary-password",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.repository.created_msp_users, [(
            "operator@example.com", "temporary-password", "Operator",
            "MSP_OPERATOR", None, "user-1",
        )])

    def test_msp_admin_can_explicitly_scope_new_msp_user(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        response = self.client.post(
            "/msp/users/platform",
            data={
                "csrf_token": "csrf-token",
                "email": "public-operator@example.com",
                "display_name": "Public Operator",
                "role": "MSP_OPERATOR",
                "environment_scope": "public",
                "password": "temporary-password",
                "password_confirmation": "temporary-password",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.repository.created_msp_users, [(
            "public-operator@example.com",
            "temporary-password",
            "Public Operator",
            "MSP_OPERATOR",
            "public",
            "user-1",
        )])

    def test_public_scoped_admin_cannot_access_gov_tenant_or_report(self):
        self.use_scoped_msp("MSP_ADMIN", "public")
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        original_tenant_detail = self.repository.tenant_detail

        def tenant_detail(tenant_id):
            if tenant_id == "tenant-gov":
                return {
                    "id": "tenant-gov",
                    "environment": "gov",
                    "customer_code": "gov-customer",
                    "customer_name": "Gov Customer",
                    "status": "ACTIVE",
                }
            return original_tenant_detail(tenant_id)

        self.repository.tenant_detail = tenant_detail

        detail = self.client.get("/msp/customer/tenant-gov")
        report = self.client.get("/reports/report-gov")
        deletion = self.client.post(
            "/reports/report-gov/delete",
            data={"csrf_token": "csrf-token"},
        )
        mutation = self.client.post(
            "/msp/customer/tenant-gov/logo/delete",
            data={"csrf_token": "csrf-token"},
        )
        customer_creation = self.client.post(
            "/msp/customers/gov",
            data={"csrf_token": "csrf-token"},
        )

        self.assertEqual(detail.status_code, 404)
        self.assertEqual(report.status_code, 404)
        self.assertEqual(deletion.status_code, 404)
        self.assertEqual(mutation.status_code, 404)
        self.assertEqual(customer_creation.status_code, 404)
        self.assertEqual(self.repository.deleted_reports, [])
        self.assertEqual(self.repository.deleted_logos, [])

    def test_scoped_admin_cannot_create_global_msp_or_customer_user(self):
        self.use_scoped_msp("MSP_ADMIN", "public")
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        common = {
            "csrf_token": "csrf-token",
            "email": "new-user@example.com",
            "display_name": "New User",
            "password": "temporary-password",
            "password_confirmation": "temporary-password",
        }

        customer_user = self.client.post("/msp/users", data=common)
        global_msp = self.client.post(
            "/msp/users/platform",
            data={**common, "role": "MSP_OPERATOR", "environment_scope": ""},
        )

        self.assertEqual(customer_user.status_code, 403)
        self.assertEqual(global_msp.status_code, 403)
        self.assertEqual(self.repository.created_portal_users, [])
        self.assertEqual(self.repository.created_msp_users, [])

    def test_msp_admin_can_disable_and_enable_another_msp_user(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")

        disabled = self.client.post(
            "/msp/users/platform/msp-user-2/enabled",
            data={"csrf_token": "csrf-token", "enabled": "false"},
        )
        enabled = self.client.post(
            "/msp/users/platform/msp-user-2/enabled",
            data={"csrf_token": "csrf-token", "enabled": "true"},
        )

        self.assertEqual(disabled.status_code, 302)
        self.assertEqual(enabled.status_code, 302)
        self.assertEqual(self.repository.updated_msp_users, [
            ("msp-user-2", "user-1", False),
            ("msp-user-2", "user-1", True),
        ])

    def test_msp_admin_cannot_change_own_account_status(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")

        response = self.client.post(
            "/msp/users/platform/user-1/enabled",
            data={"csrf_token": "csrf-token", "enabled": "false"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("자신의 MSP 계정 상태".encode("utf-8"), response.data)
        self.assertEqual(self.repository.updated_msp_users, [])

    def test_msp_status_change_rejects_invalid_boolean(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")

        response = self.client.post(
            "/msp/users/platform/msp-user-2/enabled",
            data={"csrf_token": "csrf-token", "enabled": "yes"},
            follow_redirects=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("상태 요청이 올바르지 않습니다".encode("utf-8"), response.data)
        self.assertEqual(self.repository.updated_msp_users, [])

    def test_msp_admin_can_assign_customer_membership(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        response = self.client.post(
            "/msp/users/memberships",
            data={
                "csrf_token": "csrf-token",
                "user_id": "customer-user-1",
                "tenant_id": "tenant-1",
                "role": "CUSTOMER_ADMIN",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.repository.assigned_memberships, [(
            "customer-user-1", "tenant-1", "CUSTOMER_ADMIN",
        )])

    def test_msp_user_registration_rejects_password_mismatch(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        response = self.client.post(
            "/msp/users",
            data={
                "csrf_token": "csrf-token",
                "email": "new-user@example.com",
                "display_name": "New User",
                "password": "temporary-password",
                "password_confirmation": "different-password",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.repository.created_portal_users, [])

    def test_msp_can_open_global_schedule_and_history_pages(self):
        self.assertEqual(self.client.get("/msp/schedules").status_code, 200)
        self.assertEqual(self.client.get("/history").status_code, 200)

    def test_msp_admin_can_bulk_create_schedules(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        account_id = "11111111-1111-1111-1111-111111111111"

        response = self.client.post(
            "/msp/schedules/bulk",
            data={
                "csrf_token": "csrf-token",
                "action": "create",
                "account_id": account_id,
                "report_type": "DAILY",
                "run_hour": "9",
                "run_minute": "0",
                "monthly_day": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.jobs.bulk_upserts, [(
            [account_id], "DAILY", 9, 0, 1, "user-1",
        )])

    def test_msp_admin_can_bulk_delete_schedules(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        account_id = "11111111-1111-1111-1111-111111111111"

        response = self.client.post(
            "/msp/schedules/bulk",
            data={
                "csrf_token": "csrf-token",
                "action": "delete",
                "account_id": account_id,
                "report_type": "MONTHLY",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.jobs.bulk_deletes, [([account_id], "MONTHLY")]
        )

    def test_msp_admin_can_delete_an_account_credential(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        response = self.client.post(
            "/msp/customer/tenant-1/credentials/account-1/delete",
            data={
                "csrf_token": "csrf-token",
                "confirm_account_code": "primary",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.repository.deleted_credentials,
            [("tenant-1", "account-1", "user-1")],
        )

    def test_credential_delete_requires_exact_account_code(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        response = self.client.post(
            "/msp/customer/tenant-1/credentials/account-1/delete",
            data={
                "csrf_token": "csrf-token",
                "confirm_account_code": "wrong",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.repository.deleted_credentials, [])

    def test_msp_admin_can_soft_delete_customer(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        response = self.client.post(
            "/msp/customer/tenant-1/delete",
            data={
                "csrf_token": "csrf-token",
                "confirm_customer_code": "customer",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.repository.offboarded_tenants,
            [("tenant-1", "user-1")],
        )

    def test_msp_admin_can_reactivate_offboarded_customer(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        response = self.client.post(
            "/msp/customer/tenant-1/reactivate",
            data={
                "csrf_token": "csrf-token",
                "confirm_customer_code": "customer",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.repository.reactivated_tenants,
            [("tenant-1", "user-1")],
        )

    def test_msp_admin_anonymization_requires_code_and_phrase(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        rejected = self.client.post(
            "/msp/customer/tenant-1/anonymize",
            data={
                "csrf_token": "csrf-token",
                "confirm_customer_code": "customer",
                "confirm_phrase": "wrong",
            },
        )
        accepted = self.client.post(
            "/msp/customer/tenant-1/anonymize",
            data={
                "csrf_token": "csrf-token",
                "confirm_customer_code": "customer",
                "confirm_phrase": "익명화",
            },
        )

        self.assertEqual(rejected.status_code, 302)
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(
            self.repository.anonymized_tenants,
            [("tenant-1", "user-1")],
        )

    def test_msp_admin_permanent_delete_requires_two_confirmations(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        response = self.client.post(
            "/msp/customer/tenant-1/permanent-delete",
            data={
                "csrf_token": "csrf-token",
                "confirm_customer_code": "customer",
                "confirm_phrase": "영구 삭제",
                "archive_reference": "s3://archive/customer/report.json",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.repository.permanently_deleted_tenants,
            [("tenant-1", "user-1", "s3://archive/customer/report.json", False)],
        )

    def test_msp_admin_can_force_delete_test_customer_with_reports(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        response = self.client.post(
            "/msp/customer/tenant-1/permanent-delete",
            data={
                "csrf_token": "csrf-token",
                "confirm_customer_code": "customer",
                "confirm_phrase": "강제 삭제",
                "force_delete": "true",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.repository.permanently_deleted_tenants,
            [("tenant-1", "user-1", "", True)],
        )

    def test_force_delete_requires_force_confirmation_phrase(self):
        self.client.set_cookie(CSRF_COOKIE, "csrf-token")
        response = self.client.post(
            "/msp/customer/tenant-1/permanent-delete",
            data={
                "csrf_token": "csrf-token",
                "confirm_customer_code": "customer",
                "confirm_phrase": "영구 삭제",
                "force_delete": "true",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.repository.permanently_deleted_tenants, [])

    def test_msp_portal_uses_all_customers_without_memberships(self):
        response = self.client.get("/portal")

        self.assertEqual(response.status_code, 200)
        self.assertIn("전체 고객 및 보고서".encode("utf-8"), response.data)
        self.assertIn(b"Customer", response.data)
        self.assertIn("상세/생성".encode("utf-8"), response.data)
        self.assertNotIn("일일 보고서 생성".encode("utf-8"), response.data)


if __name__ == "__main__":
    unittest.main()
