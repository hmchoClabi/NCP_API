import unittest

from app.collection_diagnostics import (
    diagnostic_service_name,
    normalize_collection_issue,
)
from app.ncp_permission_hints import PERMISSION_HINTS
from utils.provider_permissions import (
    extract_provider_code,
    extract_required_actions,
)


class ProviderPermissionParsingTests(unittest.TestCase):
    def test_actions_only_come_from_explicit_error_messages(self):
        response = {
            "resource": {
                "description": "View/getServerInstanceList",
                "message": "View/getVpcList",
            },
            "error": {
                "devMessage": "Grant View/getDomainList to the Sub Account.",
            },
        }

        self.assertEqual(
            extract_required_actions(response),
            ("View/getDomainList",),
        )

    def test_error_envelope_supports_description_and_return_message(self):
        response = {
            "responseError": {
                "description": "Grant View/getWAFList.",
                "returnMessage": "Also grant View/getDomainList.",
            },
        }

        self.assertEqual(
            extract_required_actions(response),
            ("View/getWAFList", "View/getDomainList"),
        )

    def test_success_message_is_not_treated_as_permission_error(self):
        self.assertEqual(
            extract_required_actions(
                {
                    "returnCode": 0,
                    "message": "Resource label View/getVpcList",
                }
            ),
            (),
        )

    def test_provider_code_is_bounded_and_accepts_depth_five(self):
        forged = {"error": {"errorCode": "X00004\nforged"}}
        nested = {"a": {"b": {"c": {"d": {"e": {"errorCode": "X00004"}}}}}}

        self.assertIsNone(extract_provider_code(forged))
        self.assertEqual(extract_provider_code(nested), "X00004")

    def test_error_envelope_code_precedes_business_resource_code(self):
        self.assertEqual(
            extract_provider_code(
                {
                    "resource": {"code": "RESOURCE_OK"},
                    "error": {"errorCode": "X00004"},
                }
            ),
            "X00004",
        )

    def test_generic_error_envelope_code_precedes_nested_business_code(self):
        self.assertEqual(
            extract_provider_code(
                {
                    "resource": {"returnCode": "RESOURCE_STATE"},
                    "error": {"code": "X00004"},
                }
            ),
            "X00004",
        )

    def test_confirmed_root_error_supports_description_message(self):
        self.assertEqual(
            extract_required_actions(
                {
                    "errorCode": "X00004",
                    "description": "Grant View/getDomainList.",
                }
            ),
            ("View/getDomainList",),
        )

    def test_nested_resource_description_in_error_details_is_not_trusted(self):
        self.assertEqual(
            extract_required_actions(
                {
                    "error": {
                        "message": "Permission denied.",
                        "details": {
                            "resource": {
                                "description": "View/getVpcList",
                            },
                        },
                    },
                }
            ),
            (),
        )


class CollectionDiagnosticTests(unittest.TestCase):
    def test_uses_exact_cdb_engine_from_inventory_target_type(self):
        issue = normalize_collection_issue(
            {
                "collector": "InfrastructureCollector",
                "target_type": "cdb_postgresql",
                "api": "get_cloud_postgresql_instance_list",
                "target_id": "db-123",
            }
        )

        self.assertEqual(issue["service_name"], "Cloud DB for PostgreSQL")
        self.assertEqual(issue["target"], "Cloud DB for PostgreSQL · db-123")
        self.assertEqual(issue["severity"], "error")
        self.assertEqual(issue["severity_label"], "오류")

    def test_cloud_insight_product_has_priority_over_generic_target(self):
        issue = normalize_collection_issue(
            {
                "collector": "InfrastructureMetricCollector",
                "target_type": "infrastructure_metric",
                "category": "CLOUD_DB",
                "product_name": "System/Cloud DB for MySQL(VPC)",
                "severity": "WARNING",
            }
        )

        self.assertEqual(issue["service_name"], "Cloud DB for MySQL")
        self.assertEqual(issue["target"], "Cloud DB for MySQL")
        self.assertEqual(issue["severity"], "warning")
        self.assertEqual(issue["severity_label"], "경고")

    def test_uses_exact_cache_and_serverless_product_names(self):
        cases = (
            ("System/Cloud DB for Cache(VPC)", "Cloud DB for Cache"),
            ("System/Cloud DB Serverless(VPC)", "Cloud DB Serverless"),
        )

        for product_name, expected in cases:
            with self.subTest(product_name=product_name):
                self.assertEqual(
                    diagnostic_service_name({"product_name": product_name}),
                    expected,
                )

    def test_maps_dns_load_balancer_and_storage_products(self):
        cases = (
            ({"target_type": "global_dns"}, "Global DNS"),
            ({"target_type": "load_balancer"}, "Load Balancer"),
            ({"target_type": "block_storage"}, "Block Storage"),
            ({"target_type": "server"}, "Server"),
            ({"target_type": "cdn_plus"}, "CDN+"),
        )

        for payload, expected in cases:
            with self.subTest(payload=payload):
                self.assertEqual(diagnostic_service_name(payload), expected)

    def test_uses_attempted_cloud_insight_products_for_mapping_warning(self):
        issue = normalize_collection_issue(
            {
                "target_type": "infrastructure_metric",
                "category": "CLOUD_DB",
                "attempted_products": [
                    "System/Cloud DB for PostgreSQL(VPC)",
                    "System/Cloud DB for PostgreSQL(VPC)",
                ],
                "severity": "warning",
            }
        )

        self.assertEqual(issue["target"], "Cloud DB for PostgreSQL")

    def test_event_collector_is_mapped_to_its_ncp_product(self):
        self.assertEqual(
            diagnostic_service_name(
                {
                    "collector": "ActivityTracerEventCollector",
                    "target_type": "event",
                }
            ),
            "Cloud Activity Tracer",
        )

    def test_unknown_payload_remains_explicitly_traceable(self):
        issue = normalize_collection_issue({"api": "unknown_operation"})

        self.assertEqual(issue["target"], "대상 미확인")
        self.assertEqual(issue["called_api"], "unknown_operation")

    def test_legacy_payload_without_api_is_marked_explicitly(self):
        issue = normalize_collection_issue(
            {
                "collector": "InfrastructureCollector",
                "status_code": 403,
            }
        )

        self.assertEqual(
            issue["called_api"],
            "API 미확인 (구형 진단 데이터)",
        )

    def test_historical_snapshot_diagnostic_uses_internal_source_label(self):
        issue = normalize_collection_issue(
            {
                "collector": "InfrastructureCollector",
                "stage": "historical_snapshot_lookup",
            }
        )

        self.assertEqual(issue["called_api"], "내부 저장 스냅샷 판정")

    def test_generic_403_uses_api_catalog_as_permission_recommendation(self):
        issue = normalize_collection_issue(
            {
                "collector": "InfrastructureCollector",
                "target_type": "cdb_postgresql",
                "api": "get_cloud_postgresql_instance_list",
                "status_code": 403,
                "message": "권한이 없거나 현재 환경에서 지원되지 않는 API입니다.",
            }
        )

        self.assertEqual(issue["permission_source"], "api_catalog")
        self.assertEqual(
            issue["permission_actions"],
            ["View/getDBServiceList"],
        )
        self.assertEqual(
            issue["permission_service_name"],
            "Cloud DB for PostgreSQL",
        )
        self.assertEqual(
            issue["permission_managed_policy"],
            "NCP_VPC_CLOUD_DB_FOR_POSTGRESQL_VIEWER",
        )

    def test_provider_required_action_has_priority_over_catalog(self):
        issue = normalize_collection_issue(
            {
                "collector": "InfrastructureCollector",
                "target_type": "global_dns",
                "api": "get_domain",
                "status_code": 400,
                "error_code": "X00004",
                "required_actions": ["View/getDomainList"],
                "message": "Sub Account에 자원 조회 권한이 없습니다.",
            }
        )

        self.assertEqual(issue["permission_source"], "provider_response")
        self.assertEqual(
            issue["permission_actions"],
            ["View/getDomainList"],
        )

    def test_related_actions_are_included_for_target_list(self):
        issue = normalize_collection_issue(
            {
                "target_type": "target_group",
                "api": "get_target_list",
                "status_code": 403,
            }
        )

        self.assertEqual(
            issue["permission_related_actions"],
            ["View/getTargetGroupList", "View/getTargetGroupDetail"],
        )

    def test_unknown_403_does_not_invent_a_permission_name(self):
        issue = normalize_collection_issue(
            {
                "api": "unknown_operation",
                "status_code": 403,
            }
        )

        self.assertEqual(issue["permission_source"], "unknown")
        self.assertEqual(issue["permission_actions"], [])

    def test_non_permission_failures_do_not_show_permission_candidates(self):
        cases = (
            {"target_type": "server", "api": "get_server_instance_list", "status_code": 500},
            {"target_type": "global_dns", "api": "get_domain", "status_code": 404},
            {
                "target_type": "server",
                "api": "get_server_instance_list",
                "status_code": 401,
                "error_code": "200",
                "message": "Authentication Failed",
            },
        )

        for payload in cases:
            with self.subTest(payload=payload):
                issue = normalize_collection_issue(payload)
                self.assertEqual(
                    issue["permission_source"],
                    "not_applicable",
                )
                self.assertEqual(issue["permission_actions"], [])

    def test_permission_denied_provider_codes_are_recognized(self):
        cases = (
            (401, "210"),
            (404, "300"),
        )

        for status_code, error_code in cases:
            with self.subTest(status_code=status_code, error_code=error_code):
                issue = normalize_collection_issue(
                    {
                        "target_type": "server",
                        "api": "get_server_instance_list",
                        "status_code": status_code,
                        "error_code": error_code,
                    }
                )
                self.assertEqual(issue["permission_source"], "api_catalog")

    def test_untrusted_provider_action_is_not_rendered_as_confirmed(self):
        issue = normalize_collection_issue(
            {
                "target_type": "global_dns",
                "api": "get_domain",
                "status_code": 403,
                "required_actions": [
                    "<script>alert(1)</script>",
                    "View/getDomainList",
                    "View/getDomainList",
                ],
            }
        )

        self.assertEqual(issue["permission_source"], "provider_response")
        self.assertEqual(
            issue["permission_actions"],
            ["View/getDomainList"],
        )

    def test_provider_write_action_is_separated_from_view_recommendation(self):
        issue = normalize_collection_issue(
            {
                "target_type": "network_interface",
                "api": "get_network_interface_instance_list",
                "status_code": 400,
                "error_code": "X00004",
                "required_actions": [
                    "View/getNetworkInterfaceList",
                    "Change/setSecondaryIP",
                ],
            }
        )

        self.assertEqual(issue["permission_source"], "provider_response")
        self.assertEqual(
            issue["permission_actions"],
            ["View/getNetworkInterfaceList"],
        )
        self.assertEqual(
            issue["permission_write_actions"],
            ["Change/setSecondaryIP"],
        )
        self.assertIn("쓰기 권한을 권고하지 않습니다", issue["permission_security_note"])

    def test_permission_catalog_only_contains_bounded_ncp_actions(self):
        for key, hint in PERMISSION_HINTS.items():
            with self.subTest(key=key):
                self.assertTrue(hint.actions)
                for action in hint.actions + hint.related_actions:
                    self.assertRegex(
                        action,
                        r"^View/[A-Za-z][A-Za-z0-9_-]{0,99}$",
                    )

    def test_current_collection_apis_have_permission_catalog_entries(self):
        expected = {
            ("server", "get_server_instance_list"),
            ("network_interface", "get_network_interface_instance_list"),
            ("block_storage", "get_block_storage_instance_list"),
            ("vpc", "get_vpc_list"),
            ("subnet", "get_subnet_list"),
            ("route_table", "get_route_table_list"),
            ("route_table_subnet", "get_route_table_subnet_list"),
            ("route_table_route", "get_route_list"),
            ("access_control_group", "get_access_control_group_list"),
            (
                "access_control_group_rule",
                "get_access_control_group_rule_list",
            ),
            ("network_acl", "get_network_acl_list"),
            ("network_acl_rule", "get_network_acl_rule_list"),
            ("nat_gateway", "get_nat_gateway_instance_list"),
            ("vpc_peering", "get_vpc_peering_instance_list"),
            ("public_ip", "get_public_ip_instance_list"),
            (
                "block_storage_snapshot",
                "get_block_storage_snapshot_instance_list",
            ),
            ("server_image", "get_member_server_instance_list"),
            ("global_dns", "get_domain"),
            ("certificate", "get_certificate_list"),
            ("load_balancer", "get_load_balancer_instance_list"),
            ("target_group", "get_target_group_list"),
            ("target_group", "get_target_list"),
            ("nas_vpc", "get_nas_volume_instance_list"),
            ("cdb_mysql", "get_cloud_mysql_instance_list"),
            ("cdb_postgresql", "get_cloud_postgresql_instance_list"),
            ("cdb_mssql", "get_cloud_mssql_instance_list"),
            ("cdb_mongodb", "get_cloud_mongodb_instance_list"),
            ("cdb_cache", "get_cloud_cache_instance_list"),
            ("nks", "get_nks_cluster_list"),
            ("resource_manager", "get_resource_list"),
            ("infrastructure_metric", "get_system_schema_key_list"),
            ("infrastructure_metric", "get_search_metric_list"),
            ("infrastructure_metric", "get_query_data_multiple"),
            ("event", "get_search_event"),
            ("event", "get_activity_list"),
        }

        self.assertTrue(expected.issubset(PERMISSION_HINTS.keys()))


if __name__ == "__main__":
    unittest.main()
