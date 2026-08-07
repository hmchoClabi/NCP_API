import json
import unittest

from app.customer import CustomerProfile
from app.report_options import (
    MAX_DIAGRAM_MAX_NODES,
    MONITORING_CATEGORY_OPTIONS,
    REPORT_SECTION_OPTIONS,
    RESOURCE_CATEGORY_OPTIONS,
    ReportOptions,
    normalize_report_options,
    validate_report_options,
)


class ReportOptionsTests(unittest.TestCase):
    def test_missing_options_enable_all_current_capabilities(self):
        options = normalize_report_options(None)

        self.assertEqual(options["sections"], list(REPORT_SECTION_OPTIONS))
        self.assertEqual(
            options["resource_categories"], list(RESOURCE_CATEGORY_OPTIONS)
        )
        self.assertEqual(
            options["monitoring_categories"],
            list(MONITORING_CATEGORY_OPTIONS),
        )
        self.assertTrue(options["diagram"]["show_resource_id"])
        self.assertTrue(options["diagram"]["show_private_ip"])
        self.assertTrue(options["diagram"]["show_public_ip"])

    def test_unknown_values_and_keys_are_discarded(self):
        options = normalize_report_options({
            "sections": ["billing", "run_arbitrary_collector"],
            "resource_categories": ["SERVER", "IAM_USER", "SECRET_KEY"],
            "monitoring_categories": ["SERVER", "UNKNOWN"],
            "diagram": {
                "show_resource_id": False,
                "show_unverified_relationships": True,
                "template": "{{ secret_key }}",
            },
            "command": "collect-everything",
        })

        self.assertEqual(options["sections"], ["billing"])
        self.assertEqual(options["resource_categories"], ["SERVER"])
        self.assertEqual(options["monitoring_categories"], ["SERVER"])
        self.assertFalse(options["diagram"]["show_resource_id"])
        self.assertNotIn("show_unverified_relationships", options["diagram"])
        self.assertNotIn("template", options["diagram"])
        self.assertNotIn("command", options)

    def test_diagram_max_nodes_is_bounded_and_boolean_is_strict(self):
        options = normalize_report_options({
            "diagram": {
                "enabled": "true",
                "show_public_ip": False,
                "max_nodes": 9999,
            }
        })

        self.assertTrue(options["diagram"]["enabled"])
        self.assertFalse(options["diagram"]["show_public_ip"])
        self.assertEqual(
            options["diagram"]["max_nodes"], MAX_DIAGRAM_MAX_NODES
        )

    def test_explicit_settings_require_a_section(self):
        with self.assertRaisesRegex(ValueError, "섹션"):
            validate_report_options({
                "sections": [],
                "resource_categories": [],
                "monitoring_categories": [],
                "diagram": {},
            })

    def test_helper_exposes_collector_decisions(self):
        options = ReportOptions({
            "sections": ["billing", "monitoring"],
            "resource_categories": ["SERVER", "VPC"],
            "monitoring_categories": ["SERVER"],
            "diagram": {"enabled": False, "max_nodes": 50},
        })

        self.assertTrue(options.section_enabled("billing"))
        self.assertFalse(options.section_enabled("activity_history"))
        self.assertTrue(options.resource_enabled("server"))
        self.assertFalse(options.resource_enabled("CLOUD_DB"))
        self.assertTrue(options.monitoring_enabled("server"))
        self.assertFalse(options.monitoring_enabled("LOAD_BALANCER"))
        self.assertFalse(options.diagram_option("enabled"))

    def test_customer_snapshot_contains_normalized_options_without_credentials(self):
        customer = CustomerProfile(
            customer_id="customer-one",
            customer_name="Customer One",
            report_options={
                "sections": ["billing"],
                "resource_categories": ["SERVER"],
                "monitoring_categories": [],
                "diagram": {"show_resource_id": False},
            },
        )

        snapshot = customer.to_dict()
        serialized = json.dumps(snapshot).casefold()
        self.assertEqual(snapshot["report_options"]["sections"], ["billing"])
        self.assertNotIn("access_key", serialized)
        self.assertNotIn("secret_key", serialized)


if __name__ == "__main__":
    unittest.main()
