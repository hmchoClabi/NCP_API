import unittest

import requests

from collectors.billingcollector import BillingCollector
from normalizers.billingnormalizer import BillingNormalizer


class FakeFactory:
    def __init__(self, platform):
        self.platform = platform

    def get(self, name):
        if name != "platform":
            raise KeyError(name)
        return self.platform


class BillingPlatformStub:
    LIST_KEYS = {
        "get_demand_cost_list": "demandCostList",
        "get_product_demand_cost_list": "productDemandCostList",
        "get_contract_demand_cost_list": "contractDemandCostList",
        "get_contract_usage_list_by_daily": "contractUsageListByDaily",
        "get_contract_usage_list": "contractList",
        "get_product_price_list": "productPriceList",
        "get_product_demand_cost_by_discount_list": (
            "productDemandCostByDiscountList"
        ),
        "get_discount_list": "discountList",
        "get_credit_history_list": "creditHistoryList",
        "get_product_discount_history_list": "productDiscountHistoryList",
        "get_coin_history_list": "coinHistoryList",
        "get_price_list": "priceList",
    }
    WRAPPER_KEYS = {
        method_name: (
            "get"
            + "".join(
                part[:1].upper() + part[1:]
                for part in method_name.removeprefix("get_").split("_")
            )
            + "Response"
        )
        for method_name in LIST_KEYS
    }

    def __init__(self, failing_method=None, error_method=None):
        self.failing_method = failing_method
        self.error_method = error_method
        self.calls = []

    def __getattr__(self, name):
        if name not in self.LIST_KEYS:
            raise AttributeError(name)

        def request(*args, **kwargs):
            self.calls.append((name, kwargs))
            if name == self.failing_method:
                raise RuntimeError(
                    "request failed with url: "
                    "/billing?privateKey=do-not-store"
                )

            rows = (
                [{"discountNo": "discount-1"}]
                if name == "get_discount_list"
                else []
            )
            return {
                self.WRAPPER_KEYS[name]: {
                    "returnCode": (
                        "999"
                        if name == self.error_method
                        else "0"
                    ),
                    "totalRows": len(rows),
                    self.LIST_KEYS[name]: rows,
                }
            }

        return request


class BillingNormalizerTests(unittest.TestCase):
    def setUp(self):
        self.normalizer = BillingNormalizer()

    def test_zero_values_are_not_replaced_by_fallback_fields(self):
        confirmed = self.normalizer.summarize_confirmed_by_service(
            [
                {
                    "productDemandType": {"codeName": "Server"},
                    "useAmount": 100,
                    "demandAmount": 0,
                }
            ]
        )
        self.assertEqual(confirmed[0]["amount"], 0.0)

        usage_row = {
            "usage": {
                "userUsageQuantity": 0,
                "usageQuantity": 10,
            }
        }
        self.assertEqual(self.normalizer.get_usage_quantity(usage_row), 0.0)
        self.assertEqual(
            self.normalizer.get_price({"price": 0, "unitPrice": 10}),
            0.0,
        )

    def test_member_discount_fields_are_included_consistently(self):
        result = self.normalizer.summarize_discount_by_service(
            [
                {
                    "productDemandType": {"codeName": "Server"},
                    "memberPriceDiscountAmount": 3,
                    "memberPromiseDiscountAddAmount": 2,
                }
            ]
        )
        self.assertEqual(result[0]["total_discount_amount"], 5.0)
        self.assertEqual(result[0]["member_price_discount_amount"], 3.0)
        self.assertEqual(
            result[0]["member_promise_discount_add_amount"],
            2.0,
        )

    def test_missing_price_is_reported_and_excluded_from_verified_total(self):
        usage_row = {
            "contract": {"contractType": {"codeName": "Server"}},
            "contractProduct": {
                "priceNo": "missing",
                "productRatingType": {"codeName": "CPU", "code": "CPU"},
            },
            "usage": {
                "userUsageQuantity": 2,
                "userUnit": {"code": "HOUR", "codeName": "hour"},
            },
        }
        result = self.normalizer.normalize(
            {
                "product_demand_cost": [],
                "product_demand_cost_by_discount": [],
                "daily_usage": [{"contractUsageListByDaily": [usage_row]}],
                "price_list": [],
                "discount_list": [],
            },
            billing_month="202601",
        )
        self.assertEqual(
            result["expected_cost_summary"][0]["calculation_status"],
            "PRICE_NOT_FOUND",
        )
        self.assertEqual(result["summary"]["expected_total_amount"], 0.0)
        self.assertEqual(
            result["summary"]["calculation_status_counts"],
            {"PRICE_NOT_FOUND": 1},
        )
        self.assertEqual(
            result["summary"]["comparison_status"],
            "PARTIAL_UNVERIFIED_EXPECTED_COST",
        )
        self.assertIsNone(result["summary"]["diff_amount"])
        self.assertEqual(result["comparison_summary"], [])

    def test_expected_list_price_compares_with_pre_discount_use_amount(self):
        usage_row = {
            "contract": {"contractType": {"codeName": "Server"}},
            "contractProduct": {
                "priceNo": "price-1",
                "productRatingType": {"codeName": "CPU", "code": "CPU"},
            },
            "usage": {
                "userUsageQuantity": 10,
                "userUnit": {"code": "HOUR", "codeName": "hour"},
            },
        }
        result = self.normalizer.normalize(
            {
                "product_demand_cost": [
                    {
                        "productDemandCostList": [
                            {
                                "productDemandType": {
                                    "codeName": "Server",
                                },
                                "useAmount": 100,
                                "demandAmount": 80,
                            }
                        ]
                    }
                ],
                "product_demand_cost_by_discount": [],
                "daily_usage": [
                    {"contractUsageListByDaily": [usage_row]}
                ],
                "price_list": [
                    {
                        "priceList": [
                            {
                                "priceNo": "price-1",
                                "price": 10,
                                "priceUnitType": {"code": "USAGE_HH"},
                            }
                        ]
                    }
                ],
                "discount_list": [],
            },
            billing_month="202601",
        )

        summary = result["summary"]
        self.assertEqual(summary["confirmed_total_amount"], 80.0)
        self.assertEqual(summary["confirmed_use_total_amount"], 100.0)
        self.assertEqual(summary["expected_total_amount"], 100.0)
        self.assertEqual(summary["diff_amount"], 0.0)
        self.assertEqual(summary["comparison_status"], "OK")
        comparison = result["comparison_summary"][0]
        self.assertEqual(comparison["confirmed_amount"], 80.0)
        self.assertEqual(comparison["comparison_base_amount"], 100.0)
        self.assertEqual(comparison["diff_amount"], 0.0)

    def test_storage_usage_already_in_gb_is_not_multiplied_by_size_again(self):
        row = {
            "contract": {"contractType": {"codeName": "Storage"}},
            "contractProduct": {
                "productRatingType": {"codeName": "Storage", "code": "STG"},
                "storageSizeGb": 100,
            },
            "usage": {
                "userUsageQuantity": 2,
                "userUnit": {"code": "GBYTE_PER_MONTH_DAY"},
            },
        }
        calculated = self.normalizer.calculate_expected_amount(
            row=row,
            price_row={
                "price": 3,
                "priceUnitType": {"code": "STRG_1G_MM"},
            },
            usage_quantity=2,
            usage_unit_code="GBYTE_PER_MONTH_DAY",
            days_in_month=31,
        )
        self.assertEqual(calculated["expected_amount"], 6)
        self.assertEqual(calculated["calculation_status"], "OK")

    def test_small_product_size_is_always_converted_from_bytes(self):
        row = {
            "contractProduct": {"productSize": 12 * 1024 * 1024},
            "usage": {
                "userUsageQuantity": 24,
                "userUnit": {"code": "HOUR"},
            },
        }
        calculated = self.normalizer.calculate_expected_amount(
            row=row,
            price_row={
                "price": 0.08,
                "priceUnitType": {"code": "STRG_1G_HH"},
            },
            usage_quantity=24,
            usage_unit_code="HOUR",
            days_in_month=31,
        )

        self.assertAlmostEqual(calculated["expected_amount"], 0.0225)

    def test_confirmed_invoice_subtotal_excludes_vat(self):
        invoice = self.normalizer.summarize_confirmed_invoice(
            [{
                "useAmount": 750060,
                "rounddownDiscountAmount": 60,
                "thisMonthDemandAmount": 825000,
                "thisMonthVatAmount": 75000,
                "thisMonthAmountIncludingVat": 825000,
            }],
            "202607",
            "2026-08-07T13:00:00+09:00",
        )

        self.assertEqual(invoice["subtotal_amount"], 750000)
        self.assertEqual(invoice["vat_amount"], 75000)
        self.assertEqual(invoice["total_amount"], 825000)

    def test_organization_billing_is_split_by_member_number(self):
        def demand(member_no, amount):
            return {
                "memberNo": member_no,
                "thisMonthVatAmount": amount * 0.1,
                "thisMonthAmountIncludingVat": amount * 1.1,
            }

        result = self.normalizer.normalize(
            {
                "confirmed_demand_cost": [{
                    "demandCostList": [demand("100", 100), demand("200", 200)]
                }],
                "_meta": {
                    "organization": {
                        "scope": "ORGANIZATION",
                        "members": [
                            {"member_no": "100", "display_name": "Master", "is_master": True},
                            {"member_no": "200", "display_name": "Child", "is_master": False},
                        ],
                    }
                },
            },
            billing_month="202607",
        )

        self.assertEqual(len(result["account_costs"]), 2)
        totals = {
            row["member_no"]: row["cost_facts"][0]["total_amount"]
            for row in result["account_costs"]
        }
        self.assertEqual(totals, {"100": 110.0, "200": 220.0})

    def test_complex_rating_types_are_not_counted_as_verified_cost(self):
        usage_row = {
            "contract": {"contractType": {"codeName": "Server"}},
            "contractProduct": {
                "priceNo": "complex-price",
                "productRatingType": {"codeName": "CPU", "code": "CPU"},
            },
            "usage": {
                "userUsageQuantity": 10,
                "userUnit": {"code": "HOUR"},
            },
        }

        for rating_code in ("SECT", "PKG"):
            with self.subTest(rating_code=rating_code):
                result = self.normalizer.normalize(
                    {
                        "product_demand_cost": [
                            {
                                "productDemandCostList": [
                                    {
                                        "productDemandType": {
                                            "codeName": "Server",
                                        },
                                        "useAmount": 100,
                                        "demandAmount": 100,
                                    }
                                ]
                            }
                        ],
                        "daily_usage": [
                            {"contractUsageListByDaily": [usage_row]}
                        ],
                        "price_list": [
                            {
                                "priceList": [
                                    {
                                        "priceNo": "complex-price",
                                        "price": 10,
                                        "priceUnitType": {
                                            "code": "USAGE_HH",
                                        },
                                        "ratingUnitType": {
                                            "code": rating_code,
                                        },
                                    }
                                ]
                            }
                        ],
                    },
                    billing_month="202601",
                )

                self.assertEqual(
                    result["expected_cost_summary"][0][
                        "calculation_status"
                    ],
                    f"UNSUPPORTED_RATING_{rating_code}",
                )
                self.assertEqual(
                    result["summary"]["comparison_status"],
                    "PARTIAL_UNVERIFIED_EXPECTED_COST",
                )
                self.assertIsNone(result["summary"]["diff_amount"])

    def test_fixed_and_unknown_price_types_are_not_verified(self):
        row = {
            "contract": {"contractType": {"codeName": "Server"}},
            "contractProduct": {
                "productRatingType": {"codeName": "CPU", "code": "CPU"},
            },
            "usage": {
                "userUsageQuantity": 10,
                "userUnit": {"code": "HOUR"},
            },
        }

        for price_type_code in ("FXSUM", "UNKNOWN"):
            with self.subTest(price_type_code=price_type_code):
                calculated = self.normalizer.calculate_expected_amount(
                    row=row,
                    price_row={
                        "price": 100,
                        "priceType": {"code": price_type_code},
                        "priceUnitType": {"code": "USAGE_HH"},
                    },
                    usage_quantity=10,
                    usage_unit_code="HOUR",
                    days_in_month=31,
                )
                self.assertEqual(
                    calculated["calculation_status"],
                    f"UNSUPPORTED_PRICE_TYPE_{price_type_code}",
                )
                self.assertEqual(calculated["expected_amount"], 0.0)

    def test_free_price_type_is_explicitly_zero(self):
        calculated = self.normalizer.calculate_expected_amount(
            row={},
            price_row={
                "price": 999,
                "priceType": {"code": "FREE"},
                "priceUnitType": {"code": "USAGE_HH"},
            },
            usage_quantity=10,
            usage_unit_code="HOUR",
            days_in_month=31,
        )

        self.assertEqual(calculated["calculation_status"], "OK")
        self.assertEqual(calculated["calculation_method"], "FREE_PRICE")
        self.assertEqual(calculated["expected_amount"], 0.0)

    def test_metered_condition_price_equal_to_base_price_is_supported(self):
        calculated = self.normalizer.calculate_expected_amount(
            row={},
            price_row={
                "price": 5789,
                "priceType": {"code": "MTRAT"},
                "ratingUnitType": {"code": "POINT"},
                "priceUnitType": {"code": "USAGE_HH"},
                "conditionType": {"code": "SVR_ST_PRC"},
                "conditionPrice": 5789,
            },
            usage_quantity=2,
            usage_unit_code="HOUR",
            days_in_month=31,
        )

        self.assertEqual(calculated["calculation_status"], "OK")
        self.assertEqual(calculated["expected_amount"], 11578)

    def test_partial_period_can_disable_monthly_comparison(self):
        result = self.normalizer.normalize(
            {},
            billing_month="202601",
            comparison_enabled=False,
        )
        self.assertIsNone(result["summary"]["diff_amount"])
        self.assertIsNone(result["summary"]["diff_rate"])
        self.assertEqual(
            result["summary"]["comparison_status"],
            "SKIPPED_DIFFERENT_PERIOD_SCOPE",
        )
        self.assertEqual(result["comparison_summary"], [])

    def test_cost_facts_keep_confirmed_and_estimated_periods_separate(self):
        usage_row = {
            "useDate": {
                "useStartDate": "20260701",
                "useEndDate": "20260731",
            },
            "contract": {"contractType": {"codeName": "Server"}},
            "contractProduct": {
                "priceNo": "price-1",
                "productRatingType": {"codeName": "CPU", "code": "CPU"},
            },
            "usage": {
                "userUsageQuantity": 10,
                "userUnit": {"code": "HOUR", "codeName": "hour"},
            },
        }
        result = self.normalizer.normalize(
            {
                "confirmed_demand_cost": [{
                    "demandCostList": [{
                        "thisMonthDemandAmount": 100,
                        "thisMonthVatAmount": 10,
                        "thisMonthAmountIncludingVat": 110,
                        "totalDemandAmount": 310,
                        "payCurrency": {"code": "KRW"},
                    }]
                }],
                "product_demand_cost": [],
                "daily_usage": [{"contractUsageListByDaily": [usage_row]}],
                "month_to_date_usage": [
                    {"contractUsageListByDaily": [usage_row]}
                ],
                "price_list": [{
                    "priceList": [{
                        "priceNo": "price-1",
                        "price": 10,
                        "priceUnitType": {"code": "USAGE_HH"},
                    }]
                }],
            },
            billing_month="202607",
            report_period={
                "start_dt": "2026-07-01 00:00:00",
                "end_dt": "2026-07-31 23:59:59",
                "confirmed_demand_month": "202607",
                "target_month_closed": True,
            },
            calculated_at="2026-08-07T12:00:00+09:00",
        )

        self.assertEqual(result["invoice_summary"]["total_amount"], 110.0)
        self.assertEqual(
            result["invoice_summary"]["details"]["total_demand_amount"],
            310.0,
        )
        self.assertEqual(result["invoice_summary"]["period_start"], "2026-07-01")
        self.assertEqual(result["invoice_summary"]["period_end"], "2026-07-31")
        self.assertEqual(result["period_estimate"]["total_amount"], 100.0)
        self.assertEqual(result["period_estimate"]["coverage_end"], "2026-07-31")
        self.assertEqual(
            [fact["cost_type"] for fact in result["cost_facts"]],
            ["CONFIRMED", "PERIOD_ESTIMATE", "MONTH_TO_DATE_ESTIMATE"],
        )

    def test_rate_with_zero_base_is_not_reported_as_zero_when_value_exists(self):
        self.assertIsNone(self.normalizer.safe_rate(10, 0))
        self.assertEqual(self.normalizer.safe_rate(0, 0), 0.0)

    def test_month_end_projection_uses_actual_coverage_days(self):
        projection = self.normalizer.build_month_end_projection(
            "202608",
            False,
            {
                "status": "AVAILABLE",
                "coverage_start": "2026-08-03",
                "coverage_end": "2026-08-07",
                "total_amount": 50,
                "confidence": "VERIFIED_ESTIMATE",
                "excluded_item_count": 0,
            },
            "2026-08-07T12:00:00+09:00",
        )

        self.assertEqual(projection["details"]["observed_days"], 5)
        self.assertEqual(projection["total_amount"], 310.0)


class BillingCollectorTests(unittest.TestCase):
    def test_organization_scope_uses_integrated_query_without_member_list(self):
        platform = BillingPlatformStub()
        collector = BillingCollector(FakeFactory(platform))

        collector.collect_raw(
            use_start_date="20260801",
            use_end_date="20260801",
            demand_month="202608",
            organization_context={
                "scope": "ORGANIZATION",
                "members": [{"member_no": "100"}, {"member_no": "200"}],
            },
        )

        integrated_calls = [
            kwargs for _, kwargs in platform.calls
            if "is_organization" in kwargs
        ]
        self.assertTrue(integrated_calls)
        self.assertTrue(all(call["is_organization"] for call in integrated_calls))
        self.assertTrue(all(call["member_no_list"] is None for call in integrated_calls))

    def test_discount_return_code_2300_is_warning_not_report_error(self):
        platform = BillingPlatformStub()

        def unavailable_discount(*args, **kwargs):
            response = requests.Response()
            response.status_code = 500
            response._content = (
                b'{"responseError":{"returnCode":"2300",'
                b'"returnMessage":"not available","requestId":"request-1"}}'
            )
            raise requests.HTTPError("500 Server Error", response=response)

        platform.get_product_demand_cost_by_discount_list = unavailable_discount
        collector = BillingCollector(FakeFactory(platform))

        raw = collector.collect_raw(
            use_start_date="20260701",
            use_end_date="20260731",
            demand_month="202607",
        )

        self.assertEqual(raw["product_demand_cost_by_discount"], [])
        self.assertEqual(collector.last_errors, [])
        self.assertEqual(len(collector.last_warnings), 1)
        self.assertEqual(collector.last_warnings[0]["error_code"], "2300")
        self.assertEqual(raw["_meta"]["collection_warnings"][0]["severity"], "WARNING")

    def test_collect_paged_validates_and_stops_at_total_rows(self):
        collector = BillingCollector(FakeFactory(object()))
        calls = []

        def fetch(page_no, page_size):
            calls.append(page_no)
            return {"totalRows": 1500, "items": []}

        pages = collector.collect_paged(fetch, page_size=1000)
        self.assertEqual(len(pages), 2)
        self.assertEqual(calls, [1, 2])

        with self.assertRaises(ValueError):
            collector.collect_paged(fetch, page_size=0)

    def test_chunk_rejects_non_positive_size(self):
        collector = BillingCollector(FakeFactory(object()))
        with self.assertRaises(ValueError):
            list(collector.chunk(["1"], 0))

    def test_optional_source_failure_preserves_other_billing_results(self):
        collector = BillingCollector(
            FakeFactory(
                BillingPlatformStub(
                    failing_method="get_coin_history_list"
                )
            )
        )

        raw = collector.collect_raw(
            use_start_date="20260101",
            use_end_date="20260131",
            demand_month="202601",
        )

        self.assertEqual(raw["coin_history"], [])
        self.assertEqual(len(collector.last_errors), 1)
        self.assertFalse(
            collector.last_errors[0]["comparison_required"]
        )
        self.assertNotIn(
            "do-not-store",
            str(raw["_meta"]["collection_errors"]),
        )

    def test_core_source_failure_marks_comparison_partial(self):
        collector = BillingCollector(
            FakeFactory(
                BillingPlatformStub(
                    failing_method="get_product_demand_cost_list"
                )
            )
        )
        raw = collector.collect_raw(
            use_start_date="20260101",
            use_end_date="20260131",
            demand_month="202601",
        )

        result = BillingNormalizer().normalize(
            raw,
            billing_month="202601",
        )

        self.assertEqual(
            result["summary"]["comparison_status"],
            "PARTIAL_BILLING_COLLECTION_ERROR",
        )
        self.assertIsNone(result["summary"]["diff_amount"])
        self.assertEqual(
            result["summary"]["comparison_input_error_count"],
            1,
        )

    def test_nested_billing_error_envelope_is_not_treated_as_empty(self):
        collector = BillingCollector(
            FakeFactory(
                BillingPlatformStub(
                    error_method="get_coin_history_list"
                )
            )
        )

        raw = collector.collect_raw(
            use_start_date="20260101",
            use_end_date="20260131",
            demand_month="202601",
        )

        self.assertEqual(raw["coin_history"], [])
        self.assertTrue(
            any(
                error["source"] == "coin_history"
                for error in collector.last_errors
            )
        )


if __name__ == "__main__":
    unittest.main()
