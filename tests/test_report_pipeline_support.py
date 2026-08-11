import unittest

from app.report_options import ReportOptions
from app.report_pipeline import ObservabilityResult, build_collection_plan


class ReportPipelineSupportTest(unittest.TestCase):
    def test_collection_plan_separates_display_and_monitoring_scope(self):
        options = ReportOptions.from_value({
            "sections": ["infrastructure_inventory", "monitoring"],
            "resource_categories": ["SERVER", "VPC"],
            "monitoring_categories": ["LOAD_BALANCER"],
        })

        plan = build_collection_plan(options)

        self.assertEqual(
            plan.selected_resource_categories,
            frozenset({"SERVER", "VPC"}),
        )
        self.assertEqual(
            plan.collection_resource_categories,
            frozenset({"SERVER", "VPC", "LOAD_BALANCER"}),
        )
        self.assertEqual(
            plan.monitored_infrastructure_categories,
            frozenset({"LOAD_BALANCER"}),
        )
        self.assertTrue(plan.needs_resource_snapshot)

    def test_observability_defaults_are_not_shared(self):
        first = ObservabilityResult()
        second = ObservabilityResult()

        first.errors.append({"code": "example"})

        self.assertEqual(second.errors, [])


if __name__ == "__main__":
    unittest.main()
