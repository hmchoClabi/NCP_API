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

    def test_requested_price_rows_override_product_price_fallback(self):
        merged = self.normalizer.merge_price_rows(
            [{"priceNo": "1", "price": 10}, {"priceNo": "2", "price": 20}],
            [{"priceNo": "1", "price": 11}],
        )
        price_map = self.normalizer.build_price_map(merged)
        self.assertEqual(price_map["1"]["price"], 11)
        self.assertEqual(price_map["2"]["price"], 20)

    def test_product_price_response_is_used_when_direct_price_is_missing(self):
        usage_row = {
            "contract": {"contractType": {"codeName": "Server"}},
            "contractProduct": {
                "priceNo": "fallback-price",
                "productRatingType": {"codeName": "CPU", "code": "CPU"},
            },
            "usage": {
                "userUsageQuantity": 2,
                "userUnit": {"code": "HOUR"},
            },
        }
        result = self.normalizer.normalize(
            {
                "daily_usage": [{"contractUsageListByDaily": [usage_row]}],
                "product_price_list": [{"productPriceList": [{
                    "productCode": "server-product",
                    "priceList": [{
                        "priceNo": "fallback-price",
                        "price": 100,
                        "priceType": {"code": "MTRAT"},
                        "ratingUnitType": {"code": "POINT"},
                        "unit": {"code": "USAGE_HH"},
                    }],
                }]}],
            },
            billing_month="202608",
        )

        self.assertEqual(
            result["expected_cost_summary"][0]["expected_amount"],
            200,
        )
        self.assertEqual(
            result["expected_cost_summary"][0]["calculation_status"],
            "OK",
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

                expected_status = (
                    "UNSUPPORTED_RATING_SECT_NO_TIERS"
                    if rating_code == "SECT"
                    else "UNSUPPORTED_RATING_PKG_DIMENSION"
                )
                self.assertEqual(
                    result["expected_cost_summary"][0][
                        "calculation_status"
                    ],
                    expected_status,
                )
                self.assertEqual(
                    result["summary"]["comparison_status"],
                    "PARTIAL_UNVERIFIED_EXPECTED_COST",
                )
                self.assertIsNone(result["summary"]["diff_amount"])

    def test_package_units_without_rating_code_are_not_treated_as_point(self):
        calculated = self.normalizer.calculate_expected_amount(
            row={},
            price_row={
                "price": 100,
                "priceType": {"code": "MTRAT"},
                "unit": {"code": "USAGE_HH"},
                "packageUnitList": [{
                    "productRatingType": {"code": "NETOT"},
                    "usage": 20,
                }],
            },
            usage_quantity=10,
            usage_unit_code="HOUR",
            days_in_month=31,
        )

        self.assertEqual(
            calculated["calculation_status"],
            "UNSUPPORTED_RATING_PKG_DIMENSION",
        )
        self.assertEqual(calculated["expected_amount"], 0)

    def test_fixed_price_is_supported_and_unknown_price_type_is_not(self):
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

        fixed = self.normalizer.calculate_expected_amount(
            row=row,
            price_row={
                "price": 100,
                "priceType": {"code": "FXSUM"},
                "priceUnitType": {"code": "USAGE_HH"},
            },
            usage_quantity=10,
            usage_unit_code="HOUR",
            days_in_month=31,
        )
        self.assertEqual(fixed["calculation_status"], "OK")
        self.assertEqual(fixed["expected_amount"], 1000.0)

        unknown = self.normalizer.calculate_expected_amount(
            row=row,
            price_row={
                "price": 100,
                "priceType": {"code": "UNKNOWN"},
                "priceUnitType": {"code": "USAGE_HH"},
            },
            usage_quantity=10,
            usage_unit_code="HOUR",
            days_in_month=31,
        )
        self.assertEqual(
            unknown["calculation_status"],
            "UNSUPPORTED_PRICE_TYPE_UNKNOWN",
        )
        self.assertEqual(unknown["expected_amount"], 0.0)

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
            ["CONFIRMED", "PERIOD_ESTIMATE"],
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

    def test_stop_usage_uses_zero_condition_price(self):
        price = {
            "price": 92,
            "priceType": {"code": "MTRAT"},
            "ratingUnitType": {"code": "POINT"},
            "unit": {"code": "USAGE_HH"},
            "conditionType": {"code": "SVR_ST_PRC"},
            "conditionPrice": 0,
        }
        stop = self.normalizer.calculate_expected_amount(
            row={"usage": {"meteringType": {
                "code": "VSVRT", "codeName": "Server Stop Usage",
            }}},
            price_row=price,
            usage_quantity=24,
            usage_unit_code="HOUR",
            days_in_month=30,
        )
        running = self.normalizer.calculate_expected_amount(
            row={"usage": {"meteringType": {
                "code": "VSVR", "codeName": "Server Usage",
            }}},
            price_row=price,
            usage_quantity=1,
            usage_unit_code="HOUR",
            days_in_month=30,
        )
        self.assertEqual(stop["expected_amount"], 0.0)
        self.assertIn("CONDITION_PRICE", stop["calculation_method"])
        self.assertEqual(running["expected_amount"], 92.0)

    def test_fixed_monthly_price_uses_active_days_and_deduplicates_day(self):
        rows = []
        for day in range(1, 17):
            row = {
                "useDate": {
                    "useStartDate": f"2026-08-{day:02d}T00:00:00+0900",
                    "useEndDate": f"2026-08-{day:02d}T23:59:59+0900",
                },
                "contract": {"contractNo": "contract-1", "contractType": {
                    "codeName": "Server",
                }},
                "contractProduct": {
                    "contractProductSequence": "1",
                    "priceNo": "fixed",
                    "productRatingType": {"code": "VSVR", "codeName": "Server"},
                },
                "usage": {
                    "meteringType": {"code": "VSVR"},
                    "userUsageQuantity": 24,
                    "userUnit": {"code": "HOUR"},
                },
            }
            rows.append(row)
        rows.append(dict(rows[0]))
        summary = self.normalizer.summarize_expected_cost(
            rows,
            [{
                "priceNo": "fixed",
                "price": 100500,
                "priceType": {"code": "FXSUM"},
                "ratingUnitType": {"code": "POINT"},
                "unit": {"code": "USAGE_MM"},
                "priceDescription": (
                    "Usage time (day) * ( Price (month) / full days )"
                ),
            }],
            31,
        )
        self.assertAlmostEqual(summary[0]["expected_amount"], 51870.97, places=2)
        self.assertEqual(summary[0]["row_count"], 16)

    def test_fixed_storage_price_uses_capacity_and_active_days(self):
        rows = []
        for day in range(1, 17):
            rows.append({
                "useDate": {
                    "useStartDate": f"2026-08-{day:02d}",
                    "useEndDate": f"2026-08-{day:02d}",
                },
                "contract": {"contractNo": "storage-1", "contractType": {
                    "codeName": "Server",
                }},
                "contractProduct": {
                    "contractProductSequence": "1",
                    "priceNo": "storage",
                    "productSize": 10 * 1024 ** 3,
                    "productRatingType": {"codeName": "Storage"},
                },
                "usage": {
                    "userUsageQuantity": 24,
                    "userUnit": {"code": "HOUR"},
                },
            })
        summary = self.normalizer.summarize_expected_cost(
            rows,
            [{
                "priceNo": "storage",
                "price": 115.2,
                "priceType": {"code": "FXSUM"},
                "ratingUnitType": {"code": "POINT"},
                "unit": {"code": "STRG_1G_MM"},
                "priceDescription": "Usage time (day) * Price (day)",
            }],
            31,
        )
        self.assertAlmostEqual(summary[0]["expected_amount"], 594.58, places=2)

    def test_tiered_usage_is_aggregated_before_free_tier(self):
        rows = []
        for day in (1, 2):
            rows.append({
                "account": {"memberNo": "member-1"},
                "useDate": {
                    "useStartDate": f"2026-08-{day:02d}",
                    "useEndDate": f"2026-08-{day:02d}",
                },
                "contract": {"contractNo": f"network-{day}", "contractType": {
                    "codeName": (
                        "Server" if day == 1 else "Cloud DB for Cache"
                    ),
                }},
                "contractProduct": {
                    "priceNo": "network",
                    "productRatingType": {"code": "NETOT", "codeName": "Network OUT"},
                },
                "usage": {
                    "userUsageQuantity": 768,
                    "userUnit": {"code": "GBYTE"},
                    "meteringType": {"code": "NETOT"},
                },
            })
        summary = self.normalizer.summarize_expected_cost(
            rows,
            [{
                "priceNo": "network",
                "price": 0,
                "priceType": {"code": "MTRAT"},
                "ratingUnitType": {"code": "SECT"},
                "unit": {"code": "USAGE_1GB"},
                "periodUnitList": [
                    {"startValue": 0, "endValue": 1024 ** 4, "price": 0},
                    {"startValue": 1024 ** 4, "endValue": 5 * 1024 ** 4, "price": 100},
                    {"startValue": 5 * 1024 ** 4, "endValue": -1, "price": 90},
                ],
            }],
            31,
        )
        self.assertEqual(summary[0]["calculation_status"], "OK")
        self.assertEqual(summary[0]["expected_amount"], 51200.0)

    def test_monthly_free_value_is_applied_once_after_aggregation(self):
        rows = [{
            "account": {"memberNo": "member-1"},
            "contract": {"contractType": {"codeName": "SourceCommit"}},
            "contractProduct": {
                "priceNo": "source-storage",
                "productRatingType": {"codeName": "Storage"},
            },
            "usage": {
                "userUsageQuantity": 31,
                "userUnit": {"code": "GBYTE"},
            },
        } for _ in range(2)]
        summary = self.normalizer.summarize_expected_cost(
            rows,
            [{
                "priceNo": "source-storage",
                "price": 60,
                "priceType": {"code": "MTRAT"},
                "ratingUnitType": {"code": "POINT"},
                "unit": {"code": "USAGE_1GB"},
                "freeUnit": {"code": "SAVE_CAPA_1G"},
                "freeValue": 50,
            }],
            31,
        )
        self.assertEqual(summary[0]["expected_amount"], 720.0)

    def test_fixed_daily_price_prefers_running_row_over_stopped_row(self):
        base_row = {
            "account": {"memberNo": "member-1"},
            "useDate": {
                "useStartDate": "2026-08-01",
                "useEndDate": "2026-08-01",
            },
            "contract": {
                "contractNo": "server-1",
                "contractType": {"codeName": "Server"},
            },
            "contractProduct": {
                "contractProductSequence": "1",
                "priceNo": "fixed-server",
                "productRatingType": {"codeName": "Server"},
            },
        }
        rows = [
            {
                **base_row,
                "usage": {
                    "meteringType": {"code": "VSVRT"},
                    "userUsageQuantity": 23,
                    "userUnit": {"code": "HOUR"},
                },
            },
            {
                **base_row,
                "usage": {
                    "meteringType": {"code": "VSVR"},
                    "userUsageQuantity": 1,
                    "userUnit": {"code": "HOUR"},
                },
            },
        ]
        summary = self.normalizer.summarize_expected_cost(
            rows,
            [{
                "priceNo": "fixed-server",
                "price": 31000,
                "priceType": {"code": "FXSUM"},
                "ratingUnitType": {"code": "POINT"},
                "unit": {"code": "USAGE_MM"},
                "conditionType": {"code": "SVR_ST_PRC"},
                "conditionPrice": 0,
                "priceDescription": "Usage time (day) * Price (day)",
            }],
            31,
        )

        self.assertEqual(summary[0]["expected_amount"], 1000.0)
        self.assertEqual(summary[0]["row_count"], 1)

    def test_lb_rule_free_count_is_applied_to_rules_not_hours(self):
        price = {
            "priceNo": "lb-rule",
            "price": 9,
            "priceType": {"code": "MTRAT"},
            "ratingUnitType": {"code": "POINT"},
            "chargingUnitType": {"code": "TIME"},
            "unit": {"code": "USAGE_HH"},
            "freeUnit": {"code": "MMLY_AVG_RULE_CNT"},
            "freeValue": 5,
        }
        for count, hours, expected in ((4, 384, 0), (8, 384, 10368)):
            with self.subTest(product_count=count):
                calculated = self.normalizer.calculate_expected_amount(
                    row={
                        "contractProduct": {"productCount": count},
                        "usage": {
                            "userUsageQuantity": hours,
                            "userUnit": {"code": "HOUR"},
                        },
                    },
                    price_row=price,
                    usage_quantity=hours,
                    usage_unit_code="HOUR",
                    days_in_month=31,
                )
                self.assertEqual(calculated["expected_amount"], expected)

    def test_tiered_request_blocks_are_rounded_up_per_tier(self):
        price = {
            "priceNo": "image-optimizer",
            "price": 0,
            "priceType": {"code": "MTRAT"},
            "ratingUnitType": {"code": "SECT"},
            "chargingUnitType": {"code": "UNITS"},
            "chargingUnitBasicValue": 1000,
            "unit": {"code": "REQ_CNT"},
            "periodUnitList": [
                {"startValue": 0, "endValue": 1000, "price": 0},
                {"startValue": 1000, "endValue": 10000, "price": 2000},
                {"startValue": 10000, "endValue": 3000000, "price": 1500},
                {"startValue": 3000000, "endValue": -1, "price": 1000},
            ],
        }
        expected_amounts = {
            1000: 0,
            1001: 2000,
            1500: 2000,
            10000: 18000,
            10001: 19500,
            30000: 48000,
        }
        for quantity, expected in expected_amounts.items():
            with self.subTest(quantity=quantity):
                rows = [{
                    "account": {"memberNo": "member-1"},
                    "contract": {"contractType": {"codeName": "Image Optimizer"}},
                    "contractProduct": {
                        "priceNo": "image-optimizer",
                        "productRatingType": {"codeName": "Request"},
                    },
                    "usage": {
                        "userUsageQuantity": quantity,
                        "userUnit": {"code": "COUNT_TIMES"},
                        "meteringType": {"code": "REQ_CNT"},
                    },
                }]
                summary = self.normalizer.summarize_expected_cost(
                    rows,
                    [price],
                    31,
                )
                self.assertEqual(summary[0]["expected_amount"], expected)

    def test_section_free_value_is_not_applied_twice(self):
        rows = [{
            "account": {"memberNo": "member-1"},
            "contract": {"contractType": {"codeName": "Object Storage"}},
            "contractProduct": {
                "priceNo": "tier-with-free",
                "productRatingType": {"codeName": "Network OUT"},
            },
            "usage": {
                "userUsageQuantity": 1536,
                "userUnit": {"code": "GBYTE"},
                "meteringType": {"code": "NETOT"},
            },
        }]
        summary = self.normalizer.summarize_expected_cost(
            rows,
            [{
                "priceNo": "tier-with-free",
                "price": 0,
                "priceType": {"code": "MTRAT"},
                "ratingUnitType": {"code": "SECT"},
                "unit": {"code": "USAGE_1GB"},
                "freeUnit": {"code": "SAVE_CAPA_1G"},
                "freeValue": 1024,
                "periodUnitList": [
                    {"startValue": 0, "endValue": 1024 ** 4, "price": 0},
                    {"startValue": 1024 ** 4, "endValue": -1, "price": 100},
                ],
            }],
            31,
        )

        self.assertEqual(summary[0]["expected_amount"], 51200)
        self.assertTrue(
            summary[0]["rating_details"]["free_quantity_already_in_tiers"]
        )

    def test_description_rule_calculates_secret_manager_hourly_fallback(self):
        calculated = self.normalizer.calculate_expected_amount(
            row={},
            price_row={
                "price": 0.6,
                "priceType": {"code": "MTRAT"},
                "ratingUnitType": {"code": "POINT"},
                "unit": {"code": "REQ_CNT"},
                "meteringUnit": {"code": "USAGE_SEC"},
                "priceDescription": "Usage time (hour) * Price",
            },
            usage_quantity=14,
            usage_unit_code="HOUR",
            days_in_month=31,
        )
        self.assertEqual(calculated["calculation_status"], "INFERRED")
        self.assertEqual(calculated["expected_amount"], 8.4)

        summary = self.normalizer.summarize_expected_cost(
            [{
                "account": {"memberNo": "member-1"},
                "contract": {"contractType": {"codeName": "Secret Manager"}},
                "contractProduct": {
                    "priceNo": "secret-maintenance",
                    "productRatingType": {"codeName": "Maintenance"},
                },
                "usage": {
                    "userUsageQuantity": 14.107778,
                    "userUnit": {"code": "HOUR"},
                    "meteringType": {"code": "MAINT"},
                },
            }],
            [{
                "priceNo": "secret-maintenance",
                "price": 0.6,
                "priceType": {"code": "MTRAT"},
                "ratingUnitType": {"code": "POINT"},
                "unit": {"code": "REQ_CNT"},
                "meteringUnit": {"code": "USAGE_SEC"},
                "priceDescription": "Usage time (hour) * Price",
            }],
            31,
        )
        self.assertEqual(summary[0]["expected_amount"], 9.0)

    def test_controlled_fallback_unit_conversions(self):
        hourly_to_minutes = self.normalizer.calculate_expected_amount(
            row={},
            price_row={
                "price": 100,
                "priceType": {"code": "MTRAT"},
                "unit": {"code": "USAGE_MIN"},
            },
            usage_quantity=24,
            usage_unit_code="HOUR",
            days_in_month=31,
        )
        day_to_hours = self.normalizer.calculate_expected_amount(
            row={},
            price_row={
                "price": 100,
                "priceType": {"code": "MTRAT"},
                "unit": {"code": "USAGE_HH"},
            },
            usage_quantity=1,
            usage_unit_code="SEC_DAY",
            days_in_month=31,
        )
        self.assertEqual(hourly_to_minutes["expected_amount"], 144000)
        self.assertEqual(day_to_hours["expected_amount"], 2400)

    def test_units_charging_basic_value_uses_ceiling_blocks(self):
        rows = [{
            "account": {"memberNo": "member-1"},
            "contract": {"contractType": {"codeName": "Secret Manager"}},
            "contractProduct": {
                "priceNo": "secret-api",
                "productRatingType": {"codeName": "API Call"},
            },
            "usage": {
                "userUsageQuantity": 7500,
                "userUnit": {"code": "COUNT_TIMES"},
                "meteringType": {"code": "API_CALL"},
            },
        }]
        summary = self.normalizer.summarize_expected_cost(
            rows,
            [{
                "priceNo": "secret-api",
                "price": 5,
                "priceType": {"code": "MTRAT"},
                "ratingUnitType": {"code": "POINT"},
                "unit": {"code": "REQ_CNT"},
                "chargingUnitType": {"code": "UNITS"},
                "chargingUnitBasicValue": 1000,
            }],
            31,
        )

        self.assertEqual(summary[0]["expected_amount"], 40)

    def test_unknown_nonzero_unit_mapping_remains_excluded(self):
        calculated = self.normalizer.calculate_expected_amount(
            row={},
            price_row={
                "price": 10,
                "priceType": {"code": "MTRAT"},
                "unit": {"code": "UNKNOWN_PRICE_UNIT"},
            },
            usage_quantity=5,
            usage_unit_code="UNKNOWN_USAGE_UNIT",
            days_in_month=31,
        )
        self.assertEqual(calculated["calculation_status"], "FALLBACK")
        self.assertEqual(calculated["expected_amount"], 50)

    def test_month_projection_rerates_projected_tiered_usage(self):
        row = {
            "account": {"memberNo": "member-1"},
            "useDate": {
                "useStartDate": "2026-08-01",
                "useEndDate": "2026-08-16",
            },
            "contract": {"contractNo": "network-1", "contractType": {
                "codeName": "Server",
            }},
            "contractProduct": {
                "contractProductSequence": "1",
                "priceNo": "network",
                "serviceStartDate": "2026-08-01",
                "serviceEndDate": "2999-12-31",
                "productRatingType": {"code": "NETOT", "codeName": "Network OUT"},
            },
            "usage": {
                "usageQuantity": 800 * 1024 ** 3,
                "unit": {"code": "USAGE_1BYTE"},
                "userUsageQuantity": 800,
                "userUnit": {"code": "GBYTE"},
                "meteringType": {"code": "NETOT"},
            },
        }
        projected_rows = self.normalizer.project_usage_to_month_end(
            [row],
            self.normalizer._parse_api_date("2026-08-01"),
            self.normalizer._parse_api_date("2026-08-16"),
            self.normalizer._parse_api_date("2026-08-31"),
        )
        summary = self.normalizer.summarize_expected_cost(
            projected_rows,
            [{
                "priceNo": "network",
                "price": 0,
                "priceType": {"code": "MTRAT"},
                "ratingUnitType": {"code": "SECT"},
                "unit": {"code": "USAGE_1GB"},
                "periodUnitList": [
                    {"startValue": 0, "endValue": 1024 ** 4, "price": 0},
                    {"startValue": 1024 ** 4, "endValue": -1, "price": 100},
                ],
            }],
            31,
        )
        self.assertEqual(summary[0]["expected_amount"], 52600.0)

    def test_month_projection_keeps_latest_stopped_state(self):
        def state_row(day, metering):
            return {
                "useDate": {
                    "useStartDate": f"2026-08-{day:02d}",
                    "useEndDate": f"2026-08-{day:02d}",
                },
                "contract": {
                    "contractNo": "server-1",
                    "contractType": {"codeName": "Server"},
                },
                "contractProduct": {
                    "contractProductSequence": "1",
                    "priceNo": "fixed-server",
                    "serviceStartDate": "2026-08-01",
                    "productRatingType": {"codeName": "Server"},
                },
                "usage": {
                    "meteringType": {"code": metering},
                    "userUsageQuantity": 24,
                    "userUnit": {"code": "HOUR"},
                },
            }

        price = {
            "priceNo": "fixed-server",
            "price": 31000,
            "priceType": {"code": "FXSUM"},
            "ratingUnitType": {"code": "POINT"},
            "unit": {"code": "USAGE_MM"},
            "conditionType": {"code": "SVR_ST_PRC"},
            "conditionPrice": 0,
            "priceDescription": "Usage time (day) * Price (day)",
        }
        projected_rows = self.normalizer.project_usage_to_month_end(
            [state_row(1, "VSVR"), state_row(16, "VSVRT")],
            self.normalizer._parse_api_date("2026-08-01"),
            self.normalizer._parse_api_date("2026-08-16"),
            self.normalizer._parse_api_date("2026-08-31"),
            price_rows=[price],
        )
        summary = self.normalizer.summarize_expected_cost(
            projected_rows,
            [price],
            31,
        )

        self.assertEqual(sum(row["expected_amount"] for row in summary), 1000)

    def test_month_projection_keeps_latest_lb_rule_count(self):
        def rule_row(start_day, end_day, product_count):
            return {
                "useDate": {
                    "useStartDate": f"2026-08-{start_day:02d}",
                    "useEndDate": f"2026-08-{end_day:02d}",
                },
                "contract": {
                    "contractNo": "lb-1",
                    "contractType": {"codeName": "Load Balancer"},
                },
                "contractProduct": {
                    "contractProductSequence": "1",
                    "priceNo": "lb-rule",
                    "serviceStartDate": "2026-08-01",
                    "productCount": product_count,
                    "productRatingType": {"codeName": "Rule"},
                },
                "usage": {
                    "meteringType": {"code": "RULE"},
                    "userUsageQuantity": (end_day - start_day + 1) * 24,
                    "userUnit": {"code": "HOUR"},
                },
            }

        price = {
            "priceNo": "lb-rule",
            "price": 9,
            "priceType": {"code": "MTRAT"},
            "ratingUnitType": {"code": "POINT"},
            "chargingUnitType": {"code": "TIME"},
            "unit": {"code": "USAGE_HH"},
            "freeUnit": {"code": "MMLY_AVG_RULE_CNT"},
            "freeValue": 5,
        }
        projected_rows = self.normalizer.project_usage_to_month_end(
            [rule_row(1, 8, 4), rule_row(9, 16, 8)],
            self.normalizer._parse_api_date("2026-08-01"),
            self.normalizer._parse_api_date("2026-08-16"),
            self.normalizer._parse_api_date("2026-08-31"),
            price_rows=[price],
        )
        summary = self.normalizer.summarize_expected_cost(
            projected_rows,
            [price],
            31,
        )

        self.assertEqual(sum(row["expected_amount"] for row in summary), 14904)

    def test_current_month_uses_daily_cost_and_hides_duplicate_period(self):
        usage_row = {
            "account": {"memberNo": "member-1"},
            "useDate": {
                "useStartDate": "2026-08-01",
                "useEndDate": "2026-08-16",
            },
            "contract": {"contractNo": "server-1", "contractType": {
                "codeName": "Server (VPC)",
            }},
            "contractProduct": {
                "contractProductSequence": "1",
                "priceNo": "hourly",
                "serviceStartDate": "2026-08-01",
                "serviceEndDate": "2999-12-31",
                "productRatingType": {"codeName": "Server Usage"},
            },
            "usage": {
                "userUsageQuantity": 384,
                "userUnit": {"code": "HOUR"},
            },
        }
        result = self.normalizer.normalize(
            {
                "product_demand_cost": [{"productDemandCostList": [{
                    "productDemandType": {"codeName": "Server(VPC)"},
                    "useAmount": 100000,
                    "demandAmount": 100000,
                    "writeDate": "2026-08-16T10:00:00+09:00",
                }]}],
                "daily_usage": [{"contractUsageListByDaily": [usage_row]}],
                "month_to_date_usage": [{
                    "contractUsageListByDaily": [usage_row]
                }],
                "price_list": [{"priceList": [{
                    "priceNo": "hourly",
                    "price": 100,
                    "priceType": {"code": "MTRAT"},
                    "ratingUnitType": {"code": "POINT"},
                    "unit": {"code": "USAGE_HH"},
                }]}],
            },
            billing_month="202608",
            report_period={
                "start_dt": "2026-08-01 00:00:00",
                "end_dt": "2026-08-31 23:59:59",
                "month_to_date_start": "20260801",
                "month_to_date_end": "20260816",
                "target_month_closed": False,
            },
            calculated_at="2026-08-16T12:00:00+09:00",
        )
        self.assertEqual(result["period_estimate"]["status"], "NOT_APPLICABLE")
        self.assertEqual(
            result["month_to_date_estimate"]["amount_basis"],
            "PRE_DISCOUNT_LIST_PRICE",
        )
        self.assertEqual(result["month_to_date_estimate"]["total_amount"], 38400)
        self.assertEqual(result["month_end_projection"]["total_amount"], 136000)
        self.assertEqual(
            [fact["cost_type"] for fact in result["cost_facts"]],
            ["CONFIRMED", "MONTH_TO_DATE_ESTIMATE", "MONTH_END_PROJECTION"],
        )
        self.assertGreaterEqual(
            result["month_end_projection"]["total_amount"],
            result["month_to_date_estimate"]["total_amount"],
        )
        self.assertTrue(all(
            fact["confidence"] in {
                "CONFIRMED", "VERIFIED_ESTIMATE", "PARTIAL", "UNAVAILABLE",
            }
            for fact in result["cost_facts"]
        ))

    def test_current_complex_price_uses_fresh_ncp_partial_fallback(self):
        usage_row = {
            "account": {"memberNo": "member-1"},
            "useDate": {
                "useStartDate": "2026-08-01",
                "useEndDate": "2026-08-16",
            },
            "contract": {"contractType": {"codeName": "Complex Service"}},
            "contractProduct": {
                "priceNo": "package-price",
                "productRatingType": {"codeName": "Package"},
            },
            "usage": {
                "userUsageQuantity": 16,
                "userUnit": {"code": "COUNT_TIMES"},
            },
        }
        result = self.normalizer.normalize(
            {
                "product_demand_cost": [{"productDemandCostList": [{
                    "productDemandType": {"codeName": "Complex Service"},
                    "useAmount": 1234,
                    "writeDate": "2026-08-17T10:00:00+09:00",
                }]}],
                "daily_usage": [{"contractUsageListByDaily": [usage_row]}],
                "month_to_date_usage": [{
                    "contractUsageListByDaily": [usage_row]
                }],
                "price_list": [{"priceList": [{
                    "priceNo": "package-price",
                    "price": 100,
                    "priceType": {"code": "MTRAT"},
                    "ratingUnitType": {"code": "PKG"},
                    "unit": {"code": "REQ_CNT"},
                }]}],
            },
            billing_month="202608",
            report_period={
                "start_dt": "2026-08-01 00:00:00",
                "end_dt": "2026-08-31 23:59:59",
                "month_to_date_start": "20260801",
                "month_to_date_end": "20260816",
                "target_month_closed": False,
            },
            calculated_at="2026-08-17T12:00:00+09:00",
        )

        estimate = result["month_to_date_estimate"]
        self.assertEqual(estimate["total_amount"], 1234)
        self.assertEqual(estimate["amount_basis"], "NCP_CURRENT_USE_AMOUNT_FALLBACK")
        self.assertEqual(estimate["confidence"], "PARTIAL")
        self.assertEqual(estimate["excluded_item_count"], 1)
        self.assertEqual(result["month_end_projection"]["total_amount"], 1234)
        self.assertEqual(
            result["month_end_projection"]["amount_basis"],
            "NCP_ACCRUED_LOWER_BOUND",
        )

    def test_current_fallback_requires_every_ncp_row_to_be_fresh(self):
        cutoff = self.normalizer._parse_api_date("2026-08-16")
        self.assertTrue(self.normalizer.all_rows_written_on_or_after(
            [
                {"writeDate": "2026-08-16T10:00:00+09:00"},
                {"writeDate": "2026-08-17T10:00:00+09:00"},
            ],
            cutoff,
        ))
        self.assertFalse(self.normalizer.all_rows_written_on_or_after(
            [
                {"writeDate": "2026-08-17T10:00:00+09:00"},
                {"writeDate": "2026-08-15T10:00:00+09:00"},
            ],
            cutoff,
        ))
        self.assertFalse(self.normalizer.all_rows_written_on_or_after(
            [
                {"writeDate": "2026-08-17T10:00:00+09:00"},
                {},
            ],
            cutoff,
        ))

    def test_actual_usage_coverage_controls_month_end_projection(self):
        usage_row = {
            "account": {"memberNo": "member-1"},
            "useDate": {
                "useStartDate": "2026-08-01",
                "useEndDate": "2026-08-15",
            },
            "contract": {"contractType": {"codeName": "Server"}},
            "contractProduct": {
                "priceNo": "point-price",
                "serviceStartDate": "2026-08-01",
                "productRatingType": {"codeName": "Usage"},
            },
            "usage": {
                "userUsageQuantity": 150,
                "userUnit": {"code": "HOUR"},
            },
        }
        result = self.normalizer.normalize(
            {
                "daily_usage": [{"contractUsageListByDaily": [usage_row]}],
                "month_to_date_usage": [{
                    "contractUsageListByDaily": [usage_row]
                }],
                "price_list": [{"priceList": [{
                    "priceNo": "point-price",
                    "price": 1,
                    "priceType": {"code": "MTRAT"},
                    "ratingUnitType": {"code": "POINT"},
                    "unit": {"code": "USAGE_HH"},
                }]}],
            },
            billing_month="202608",
            report_period={
                "start_dt": "2026-08-01 00:00:00",
                "end_dt": "2026-08-16 23:59:59",
                "month_to_date_start": "20260801",
                "month_to_date_end": "20260816",
                "target_month_closed": False,
            },
            calculated_at="2026-08-16T12:00:00+09:00",
        )

        self.assertEqual(
            result["month_to_date_estimate"]["coverage_end"],
            "2026-08-15",
        )
        self.assertEqual(result["month_end_projection"]["total_amount"], 310)
        self.assertEqual(result["month_end_projection"]["details"]["observed_days"], 15)

    def test_closed_partial_month_shows_cutoff_and_full_month_amounts(self):
        usage_row = {
            "useDate": {
                "useStartDate": "2026-06-01",
                "useEndDate": "2026-06-16",
            },
            "contract": {"contractType": {"codeName": "Server"}},
            "contractProduct": {
                "priceNo": "point-price",
                "productRatingType": {"codeName": "Usage"},
            },
            "usage": {
                "userUsageQuantity": 160,
                "userUnit": {"code": "HOUR"},
            },
        }
        result = self.normalizer.normalize(
            {
                "product_demand_cost": [{"productDemandCostList": [{
                    "productDemandType": {"codeName": "Server"},
                    "useAmount": 310,
                }]}],
                "daily_usage": [{"contractUsageListByDaily": [usage_row]}],
                "month_to_date_usage": [{
                    "contractUsageListByDaily": [usage_row]
                }],
                "price_list": [{"priceList": [{
                    "priceNo": "point-price",
                    "price": 1,
                    "priceType": {"code": "MTRAT"},
                    "ratingUnitType": {"code": "POINT"},
                    "unit": {"code": "USAGE_HH"},
                }]}],
            },
            billing_month="202606",
            report_period={
                "start_dt": "2026-06-01 00:00:00",
                "end_dt": "2026-06-16 23:59:59",
                "month_to_date_start": "20260601",
                "month_to_date_end": "20260616",
                "target_month_closed": True,
            },
            calculated_at="2026-08-07T12:00:00+09:00",
        )

        self.assertEqual(result["period_estimate"]["total_amount"], 160)
        self.assertEqual(result["month_to_date_estimate"]["status"], "NOT_APPLICABLE")
        self.assertEqual(result["month_end_projection"]["total_amount"], 310)
        self.assertEqual(
            result["month_end_projection"]["amount_basis"],
            "NCP_PRODUCT_DEMAND_USE_AMOUNT",
        )

    def test_closed_month_uses_contract_cost_when_product_cost_is_missing(self):
        result = self.normalizer.normalize(
            {
                "contract_demand_cost": [{"contractDemandCostList": [{
                    "contract": {
                        "contractType": {"codeName": "Complex Service"},
                    },
                    "useAmount": 4321,
                    "demandAmount": 4000,
                }]}],
            },
            billing_month="202606",
            report_period={
                "start_dt": "2026-06-01 00:00:00",
                "end_dt": "2026-06-30 23:59:59",
                "target_month_closed": True,
            },
            calculated_at="2026-08-07T12:00:00+09:00",
        )

        self.assertEqual(result["period_estimate"]["total_amount"], 4321)
        self.assertEqual(
            result["period_estimate"]["amount_basis"],
            "NCP_CONTRACT_DEMAND_USE_AMOUNT",
        )
        self.assertEqual(len(result["contract_demand_cost_rows"]), 1)

    def test_ncp_projection_adds_only_local_incremental_usage(self):
        projected, fallback_count = self.normalizer.calibrate_month_projection(
            [{"service_name": "NCP Fixed + Variable", "use_amount": 1000}],
            {"local-service": 100},
            {"different-local-name": 200},
            observed_days=16,
            month_days=31,
        )

        self.assertEqual(projected, 1100)
        self.assertEqual(fallback_count, 0)


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
