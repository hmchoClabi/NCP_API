import json
import unittest

from app.customer import CustomerProfile
from app.report_options import (
    DEFAULT_REPORT_SECTION_ORDER,
    MONITORING_CATEGORY_OPTIONS,
    REPORT_OPTIONS_SCHEMA_VERSION,
    REPORT_SECTION_DESCRIPTIONS,
    REPORT_SECTION_OPTIONS,
    RESOURCE_CATEGORY_OPTIONS,
    ReportOptions,
    normalize_report_options,
    validate_report_options,
)


class ReportOptionsTests(unittest.TestCase):
    def test_missing_options_enable_all_current_capabilities(self):
        options = normalize_report_options(None)

        self.assertEqual(options["schema_version"], "1.4")
        self.assertEqual(options["sections"], list(REPORT_SECTION_OPTIONS))
        self.assertEqual(
            options["section_order"], list(DEFAULT_REPORT_SECTION_ORDER)
        )
        self.assertEqual(
            options["resource_categories"], list(RESOURCE_CATEGORY_OPTIONS)
        )
        self.assertEqual(
            options["monitoring_categories"],
            list(MONITORING_CATEGORY_OPTIONS),
        )

    def test_unknown_values_and_keys_are_discarded(self):
        options = normalize_report_options({
            "sections": ["billing", "run_arbitrary_collector"],
            "resource_categories": ["SERVER", "IAM_USER", "SECRET_KEY"],
            "monitoring_categories": ["SERVER", "UNKNOWN"],
            "command": "collect-everything",
        })

        self.assertEqual(options["sections"], ["billing"])
        self.assertEqual(options["resource_categories"], ["SERVER"])
        self.assertEqual(options["monitoring_categories"], ["SERVER"])
        self.assertNotIn("command", options)

    def test_current_section_order_is_filtered_deduplicated_and_completed(self):
        options = normalize_report_options({
            "schema_version": REPORT_OPTIONS_SCHEMA_VERSION,
            "sections": ["billing", "monitoring"],
            "section_order": [
                "billing",
                "unknown",
                "monitoring",
                "billing",
            ],
        })

        self.assertEqual(options["section_order"], [
            "billing",
            "monitoring",
            "executive_summary",
            "infrastructure_inventory",
            "organization_billing",
            "insight_events",
            "activity_history",
            "collection_diagnostics",
        ])
        self.assertEqual(
            ReportOptions(options).ordered_sections,
            ("billing", "monitoring"),
        )

    def test_missing_and_malformed_section_order_use_default(self):
        for section_order in (None, "billing", {"billing"}):
            with self.subTest(section_order=section_order):
                value = {"sections": ["billing"]}
                if section_order is not None:
                    value["section_order"] = section_order

                self.assertEqual(
                    normalize_report_options(value)["section_order"],
                    list(DEFAULT_REPORT_SECTION_ORDER),
                )

    def test_additive_section_order_survives_old_and_future_versions(self):
        reversed_order = list(reversed(DEFAULT_REPORT_SECTION_ORDER))

        for schema_version in ("1.3", "1.5", "999"):
            with self.subTest(schema_version=schema_version):
                options = normalize_report_options({
                    "schema_version": schema_version,
                    "sections": ["billing"],
                    "section_order": reversed_order,
                })

                self.assertEqual(
                    options["section_order"], reversed_order
                )

    def test_validation_rejects_unordered_section_order_types(self):
        with self.assertRaisesRegex(ValueError, "section_order"):
            validate_report_options({
                "sections": ["billing"],
                "section_order": {"billing"},
                "resource_categories": [],
                "monitoring_categories": [],
            })

    def test_validation_stamps_and_preserves_current_section_order(self):
        options = validate_report_options({
            "sections": ["billing", "executive_summary"],
            "section_order": ["billing", "executive_summary"],
            "resource_categories": [],
            "monitoring_categories": [],
        })

        self.assertEqual(options["schema_version"], "1.4")
        self.assertEqual(options["section_order"][:2], [
            "billing", "executive_summary",
        ])
        self.assertEqual(
            ReportOptions(options).ordered_sections,
            ("billing", "executive_summary"),
        )

    def test_analysis_requires_selected_summary_and_enabled_setting(self):
        without_summary = ReportOptions({
            "sections": ["billing"],
            "operational_analysis": {"enabled": True},
        })
        disabled = ReportOptions({
            "sections": ["executive_summary"],
            "operational_analysis": {"enabled": False},
        })
        enabled = ReportOptions({
            "sections": ["executive_summary"],
            "operational_analysis": {"enabled": True},
        })

        self.assertFalse(without_summary.analysis_enabled())
        self.assertFalse(disabled.analysis_enabled())
        self.assertTrue(enabled.analysis_enabled())

    def test_every_report_section_has_a_description(self):
        self.assertEqual(
            set(REPORT_SECTION_DESCRIPTIONS), set(REPORT_SECTION_OPTIONS)
        )

    def test_legacy_diagram_section_is_upgraded_to_inventory(self):
        options = normalize_report_options({
            "sections": ["billing", "infrastructure_diagram"],
            "resource_categories": ["SERVER"],
            "monitoring_categories": [],
        })

        self.assertEqual(
            options["sections"],
            ["billing", "infrastructure_inventory"],
        )
        self.assertNotIn("infrastructure_diagram", options["sections"])

    def test_explicit_settings_require_a_section(self):
        with self.assertRaises(ValueError):
            validate_report_options({
                "sections": [],
                "resource_categories": [],
                "monitoring_categories": [],
            })

    def test_helper_exposes_collector_decisions(self):
        options = ReportOptions({
            "sections": ["billing", "monitoring"],
            "resource_categories": ["SERVER", "VPC"],
            "monitoring_categories": ["SERVER"],
        })

        self.assertTrue(options.section_enabled("billing"))
        self.assertFalse(options.section_enabled("activity_history"))
        self.assertTrue(options.resource_enabled("server"))
        self.assertFalse(options.resource_enabled("CLOUD_DB"))
        self.assertTrue(options.monitoring_enabled("server"))
        self.assertFalse(options.monitoring_enabled("LOAD_BALANCER"))

    def test_customer_snapshot_contains_normalized_options_without_credentials(self):
        customer = CustomerProfile(
            customer_id="customer-one",
            customer_name="Customer One",
            report_options={
                "sections": ["billing"],
                "resource_categories": ["SERVER"],
                "monitoring_categories": [],
            },
        )

        snapshot = customer.to_dict()
        serialized = json.dumps(snapshot).casefold()
        self.assertEqual(snapshot["report_options"]["sections"], ["billing"])
        self.assertNotIn("access_key", serialized)
        self.assertNotIn("secret_key", serialized)

    def test_availability_threshold_order_is_validated(self):
        options = normalize_report_options(None)
        options["operational_analysis"]["thresholds"].update({
            "availability_warning_percent": 95,
            "availability_critical_percent": 99,
        })

        with self.assertRaisesRegex(ValueError, "가용성 위험 임계치"):
            validate_report_options(options)

    def test_legacy_low_utilization_thresholds_are_normalized_to_90(self):
        options = normalize_report_options({
            "operational_analysis": {
                "thresholds": {
                    "cpu_warning_percent": 80,
                    "cpu_critical_percent": 95,
                    "memory_warning_percent": 85,
                    "memory_critical_percent": 95,
                    "disk_warning_percent": 85,
                    "disk_critical_percent": 95,
                },
                "policies": {
                    "require_block_storage_encryption": True,
                },
            },
        })
        analysis = options["operational_analysis"]
        thresholds = analysis["thresholds"]

        self.assertEqual(thresholds["cpu_warning_percent"], 90)
        self.assertEqual(thresholds["memory_warning_percent"], 90)
        self.assertEqual(thresholds["disk_warning_percent"], 90)
        self.assertNotIn("policies", analysis)


if __name__ == "__main__":
    unittest.main()
