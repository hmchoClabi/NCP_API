from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple
import calendar


class BillingNormalizer:
    @staticmethod
    def as_dict(value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def first_present(*values: Any, default: Any = None) -> Any:
        for value in values:
            if value is not None and value != "":
                return value
        return default

    def normalize(
        self,
        raw_data: Dict[str, Any],
        current_month: str = None,
        billing_month: str = None,
        use_end_date: str = None,
        comparison_enabled: bool = True,
    ) -> Dict[str, Any]:

        billing_month = billing_month or current_month
        days_in_month = self.get_days_in_month(billing_month, use_end_date)
        raw_meta = self.as_dict(raw_data.get("_meta"))
        collection_errors = [
            error
            for error in raw_meta.get("collection_errors", [])
            if isinstance(error, dict)
        ]
        comparison_input_errors = [
            error
            for error in collection_errors
            if error.get("comparison_required")
        ]

        demand_rows = self.extract_rows(
            raw_data.get("product_demand_cost", []),
            "productDemandCostList",
        )

        demand_discount_rows = self.extract_rows(
            raw_data.get("product_demand_cost_by_discount", []),
            "productDemandCostByDiscountList",
        )

        daily_usage_rows = self.extract_rows(
            raw_data.get("daily_usage", []),
            "contractUsageListByDaily",
        )

        price_rows = self.extract_rows(
            raw_data.get("price_list", []),
            "priceList",
        )

        discount_rows = self.extract_rows(
            raw_data.get("discount_list", []),
            "discountList",
        )

        service_summary = self.summarize_confirmed_by_service(demand_rows)
        discount_summary = self.summarize_discount_by_service(demand_discount_rows)
        usage_summary = self.summarize_usage(daily_usage_rows)
        network_usage_summary = self.summarize_network_usage(daily_usage_rows)

        expected_cost_summary = self.summarize_expected_cost(
            usage_rows=daily_usage_rows,
            price_rows=price_rows,
            days_in_month=days_in_month,
        )

        verified_expected_rows = [
            row
            for row in expected_cost_summary
            if row.get("calculation_status") == "OK"
        ]
        expected_by_service = self.summarize_expected_by_service(
            verified_expected_rows
        )
        confirmed_total = sum(row["amount"] for row in service_summary)
        confirmed_use_total = sum(
            row["use_amount"]
            for row in service_summary
        )
        expected_total = sum(
            row["expected_amount"] for row in verified_expected_rows
        )
        expected_total_all = sum(
            row["expected_amount"] for row in expected_cost_summary
        )
        unverified_expected_amount = expected_total_all - expected_total
        calculation_status_counts = dict(
            Counter(
                row.get("calculation_status") or "UNKNOWN"
                for row in expected_cost_summary
            )
        )
        has_unverified_expected = any(
            status != "OK"
            for status in calculation_status_counts
        )
        if (
            comparison_enabled
            and not expected_cost_summary
            and confirmed_use_total != 0
        ):
            has_unverified_expected = True

        if not comparison_enabled:
            comparison_status = "SKIPPED_DIFFERENT_PERIOD_SCOPE"
        elif comparison_input_errors:
            comparison_status = "PARTIAL_BILLING_COLLECTION_ERROR"
        elif has_unverified_expected:
            comparison_status = "PARTIAL_UNVERIFIED_EXPECTED_COST"
        else:
            comparison_status = "OK"

        comparison_is_valid = comparison_status == "OK"
        comparison_summary = (
            self.compare_confirmed_and_expected(
                confirmed_summary=service_summary,
                expected_summary=expected_by_service,
            )
            if comparison_is_valid
            else []
        )

        diff_amount: Optional[float] = None
        diff_rate: Optional[float] = None
        if comparison_is_valid:
            diff_amount = round(expected_total - confirmed_use_total, 2)
            diff_rate = self.safe_rate(diff_amount, confirmed_use_total)

        return {
            "summary": {
                "billing_month": billing_month,
                "days_in_month": days_in_month,
                "confirmed_total_amount": round(confirmed_total, 2),
                "confirmed_use_total_amount": round(
                    confirmed_use_total,
                    2,
                ),
                "comparison_base_total_amount": round(
                    confirmed_use_total,
                    2,
                ),
                "comparison_basis": "PRE_DISCOUNT_USE_AMOUNT",
                "expected_total_amount": round(expected_total, 2),
                "expected_total_amount_all": round(expected_total_all, 2),
                "unverified_expected_amount": round(unverified_expected_amount, 2),
                "diff_amount": diff_amount,
                "diff_rate": diff_rate,
                "comparison_status": comparison_status,
                "calculation_status_counts": calculation_status_counts,
                "service_count": len(service_summary),
                "usage_summary_count": len(usage_summary),
                "network_usage_count": len(network_usage_summary),
                "expected_cost_count": len(expected_cost_summary),
                "discount_count": len(discount_rows),
                "collection_error_count": len(collection_errors),
                "comparison_input_error_count": len(
                    comparison_input_errors
                ),
            },
            "service_summary": service_summary,
            "discount_summary": discount_summary,
            "usage_summary": usage_summary,
            "network_usage_summary": network_usage_summary,
            "expected_cost_summary": expected_cost_summary,
            "expected_by_service": expected_by_service,
            "comparison_summary": comparison_summary,
            "discount_rows": discount_rows,
            "demand_cost_rows": demand_rows,
            "demand_discount_rows": demand_discount_rows,
            "daily_usage_rows": daily_usage_rows,
            "price_rows": price_rows,
            "collection_errors": collection_errors,
        }

    def summarize_confirmed_by_service(
        self,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        summary = defaultdict(lambda: {"amount": 0.0, "use_amount": 0.0, "discount_amount": 0.0, "row_count": 0})

        for row in rows:
            service_name = self.get_product_demand_service_name(row)

            use_amount = self.to_float(row.get("useAmount"))
            demand_amount = self.to_float(
                self.first_present(
                    row.get("demandAmount"),
                    row.get("useAmount"),
                    default=0,
                )
            )

            discount_amount = (
                self.to_float(row.get("promiseDiscountAmount"))
                + self.to_float(row.get("promotionDiscountAmount"))
                + self.to_float(row.get("etcDiscountAmount"))
                + self.to_float(row.get("productDiscountAmount"))
                + self.to_float(row.get("creditDiscountAmount"))
                + self.to_float(row.get("memberPriceDiscountAmount"))
                + self.to_float(row.get("memberPromiseDiscountAddAmount"))
            )

            summary[service_name]["amount"] += demand_amount
            summary[service_name]["use_amount"] += use_amount
            summary[service_name]["discount_amount"] += discount_amount
            summary[service_name]["row_count"] += 1

        return self.as_sorted_rows(summary, "service_name", "amount")

    def summarize_discount_by_service(
        self,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        summary = defaultdict(
            lambda: {
                "use_amount": 0.0,
                "demand_amount": 0.0,
                "total_discount_amount": 0.0,
                "promise_discount_amount": 0.0,
                "promotion_discount_amount": 0.0,
                "etc_discount_amount": 0.0,
                "product_discount_amount": 0.0,
                "credit_discount_amount": 0.0,
                "member_price_discount_amount": 0.0,
                "member_promise_discount_add_amount": 0.0,
                "row_count": 0,
            }
        )

        for row in rows:
            service_name = self.get_product_demand_service_name(row)

            promise = self.to_float(row.get("promiseDiscountAmount"))
            promotion = self.to_float(row.get("promotionDiscountAmount"))
            etc = self.to_float(row.get("etcDiscountAmount"))
            product = self.to_float(row.get("productDiscountAmount"))
            credit = self.to_float(row.get("creditDiscountAmount"))
            member_price = self.to_float(row.get("memberPriceDiscountAmount"))
            member_promise = self.to_float(
                row.get("memberPromiseDiscountAddAmount")
            )

            total_discount = (
                promise
                + promotion
                + etc
                + product
                + credit
                + member_price
                + member_promise
            )

            summary[service_name]["use_amount"] += self.to_float(row.get("useAmount"))
            summary[service_name]["demand_amount"] += self.to_float(row.get("demandAmount"))
            summary[service_name]["total_discount_amount"] += total_discount
            summary[service_name]["promise_discount_amount"] += promise
            summary[service_name]["promotion_discount_amount"] += promotion
            summary[service_name]["etc_discount_amount"] += etc
            summary[service_name]["product_discount_amount"] += product
            summary[service_name]["credit_discount_amount"] += credit
            summary[service_name]["member_price_discount_amount"] += member_price
            summary[service_name][
                "member_promise_discount_add_amount"
            ] += member_promise
            summary[service_name]["row_count"] += 1

        return self.as_sorted_rows(summary, "service_name", "demand_amount")

    def summarize_usage(
        self,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        summary = defaultdict(lambda: {"usage_quantity": 0.0, "row_count": 0, "unit_name": ""})

        for row in rows:
            service_name = self.get_usage_service_name(row)
            item_name = self.get_usage_item_name(row)
            item_code = self.get_usage_item_code(row)
            unit_code = self.get_usage_unit_code(row)
            unit_name = self.get_usage_unit_name(row)
            usage_quantity = self.get_usage_quantity(row)

            key = (service_name, item_name, item_code, unit_code)

            summary[key]["usage_quantity"] += usage_quantity
            summary[key]["row_count"] += 1
            summary[key]["unit_name"] = unit_name

        result = []

        for key, item in summary.items():
            service_name, item_name, item_code, unit_code = key

            if item["usage_quantity"] == 0:
                continue

            result.append(
                {
                    "service_name": service_name,
                    "item_name": item_name,
                    "item_code": item_code,
                    "usage_quantity": round(item["usage_quantity"], 6),
                    "unit_code": unit_code,
                    "unit_name": item["unit_name"],
                    "row_count": item["row_count"],
                }
            )

        return sorted(result, key=lambda x: (x["service_name"], x["item_name"]))
    
    def summarize_network_usage(
        self,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        summary = defaultdict(lambda: {"usage_gb": 0.0, "row_count": 0})

        for row in rows:
            unit_code = self.get_usage_unit_code(row)

            if unit_code != "GBYTE":
                continue

            item_name = self.get_usage_item_name(row)
            direction = self.get_network_direction(item_name)

            # 기타는 제외
            if direction == "기타":
                continue

            service_name = self.get_usage_service_name(row)

            key = (service_name, direction, item_name)

            summary[key]["usage_gb"] += self.get_usage_quantity(row)
            summary[key]["row_count"] += 1

        result = []

        for key, item in summary.items():
            service_name, direction, item_name = key

            result.append(
                {
                    "service_name": service_name,
                    "direction": direction,
                    "name": item_name,
                    "usage_gb": round(item["usage_gb"], 3),
                    "row_count": item["row_count"],
                }
            )

        return sorted(
            result,
            key=lambda x: (
                x["service_name"],
                x["direction"],
                x["name"],
            ),
        )

    def summarize_expected_cost(
        self,
        usage_rows: List[Dict[str, Any]],
        price_rows: List[Dict[str, Any]],
        days_in_month: int,
    ) -> List[Dict[str, Any]]:
        price_map = self.build_price_map(price_rows)
        summary = defaultdict(
            lambda: {
                "usage_quantity": 0.0,
                "expected_amount": 0.0,
                "row_count": 0,
                "unit_price": 0.0,
                "raw_price": 0.0,
                "storage_size_gb": 0.0,
                "price_unit_type": "",
                "charging_unit_type": "",
                "calculation_method": "",
                "calculation_status": "",
                "multiplier": 1.0,
            }
        )

        for row in usage_rows:
            price_no = self.get_price_no(row)
            price_row = price_map.get(price_no)

            service_name = self.get_usage_service_name(row)
            item_name = self.get_usage_item_name(row)
            item_code = self.get_usage_item_code(row)
            unit_code = self.get_usage_unit_code(row)
            usage_quantity = self.get_usage_quantity(row)

            if price_row:
                calculated = self.calculate_expected_amount(
                    row=row,
                    price_row=price_row,
                    usage_quantity=usage_quantity,
                    usage_unit_code=unit_code,
                    days_in_month=days_in_month,
                )
            else:
                calculated = {
                    "expected_amount": 0.0,
                    "unit_price": 0.0,
                    "calculation_method": "PRICE_LOOKUP",
                    "calculation_status": "PRICE_NOT_FOUND",
                    "multiplier": 1.0,
                }

            key = (
                service_name,
                item_name,
                item_code,
                unit_code,
                price_no,
                calculated["calculation_method"],
                calculated["calculation_status"],
                calculated["multiplier"],
            )

            summary[key]["usage_quantity"] += usage_quantity
            summary[key]["expected_amount"] += calculated["expected_amount"]
            summary[key]["row_count"] += 1
            summary[key]["unit_price"] = calculated["unit_price"]
            summary[key]["raw_price"] = self.get_price(price_row or {})
            summary[key]["storage_size_gb"] = self.get_storage_size_gb(row)
            summary[key]["price_unit_type"] = self.get_price_unit_type_code(
                price_row or {}
            )
            summary[key]["charging_unit_type"] = self.get_charging_unit_type_code(
                price_row or {}
            )
            summary[key]["calculation_method"] = calculated["calculation_method"]
            summary[key]["calculation_status"] = calculated["calculation_status"]
            summary[key]["multiplier"] = calculated["multiplier"]

        result = []

        for key, item in summary.items():
            service_name, item_name, item_code, unit_code, price_no, *_ = key

            if item["usage_quantity"] == 0 and item["expected_amount"] == 0:
                continue

            result.append(
                {
                    "service_name": service_name,
                    "item_name": item_name,
                    "item_code": item_code,
                    "price_no": price_no,
                    "usage_quantity": round(item["usage_quantity"], 6),
                    "unit_code": unit_code,
                    "raw_price": round(item["raw_price"], 10),
                    "price_unit_type": item["price_unit_type"],
                    "charging_unit_type": item["charging_unit_type"],
                    "unit_price": round(item["unit_price"], 10),
                    "multiplier": item["multiplier"],
                    "storage_size_gb": round(item["storage_size_gb"], 6),
                    "expected_amount": round(item["expected_amount"], 2),
                    "row_count": item["row_count"],
                    "calculation_method": item["calculation_method"],
                    "calculation_status": item["calculation_status"],
                }
            )

        return sorted(result, key=lambda x: x["expected_amount"], reverse=True)

    def calculate_expected_amount(
        self,
        row: Dict[str, Any],
        price_row: Dict[str, Any],
        usage_quantity: float,
        usage_unit_code: str,
        days_in_month: int,
    ) -> Dict[str, Any]:

        price = self.get_price(price_row)
        unsupported_rating_status = self.get_unsupported_rating_status(
            price_row
        )
        if unsupported_rating_status is not None:
            return {
                "expected_amount": 0.0,
                "unit_price": 0.0,
                "calculation_method": "UNSUPPORTED_COMPLEX_RATING",
                "calculation_status": unsupported_rating_status,
                "multiplier": 1.0,
            }

        if self.get_price_type_code(price_row) == "FREE":
            return {
                "expected_amount": 0.0,
                "unit_price": 0.0,
                "calculation_method": "FREE_PRICE",
                "calculation_status": "OK",
                "multiplier": 1.0,
            }

        price_unit_type = self.get_price_unit_type_code(price_row)
        storage_size_gb = self.get_storage_size_gb(row)

        service_name = self.get_usage_service_name(row)
        item_name = self.get_usage_item_name(row)
        multiplier = self.get_billing_multiplier(service_name, item_name)

        unit_price, method, status = self.resolve_unit_price(
            usage_unit_code=usage_unit_code,
            price_unit_type=price_unit_type,
            price=price,
            days_in_month=days_in_month,
        )

        amount = usage_quantity * unit_price

        if (
            price_unit_type in ("STRG_1G_HH", "STRG_1G_MM")
            and usage_unit_code == "HOUR"
        ):
            if storage_size_gb > 0:
                amount = storage_size_gb * usage_quantity * unit_price
                method = f"GB * {method}"
                status = "OK"
            else:
                status = "WARN_STORAGE_SIZE_MISSING"
        elif (
            price_unit_type in ("STRG_1G_HH", "STRG_1G_MM")
            and usage_unit_code not in ("GBYTE", "GBYTE_PER_MONTH_DAY")
        ):
            status = "FALLBACK_STORAGE_UNIT"

        amount *= multiplier

        if multiplier != 1:
            method = f"{method} * MULTIPLIER({multiplier})"

        return {
            "expected_amount": amount,
            "unit_price": unit_price,
            "calculation_method": method,
            "calculation_status": status,
            "multiplier": multiplier,
        }

    def get_unsupported_rating_status(
        self,
        price_row: Dict[str, Any],
    ) -> Optional[str]:
        price_type_code = self.get_price_type_code(price_row)
        if price_type_code and price_type_code not in {"FREE", "MTRAT"}:
            return f"UNSUPPORTED_PRICE_TYPE_{price_type_code}"

        rating_unit_type = self.as_dict(price_row.get("ratingUnitType"))
        rating_code = str(
            self.first_present(
                rating_unit_type.get("code"),
                price_row.get("ratingUnitTypeCode"),
                default="",
            )
        ).strip().upper()

        if rating_code and rating_code != "POINT":
            return f"UNSUPPORTED_RATING_{rating_code}"

        complex_list_keys = (
            "sectionPriceList",
            "periodUnitList",
            "countryUnitList",
            "packageUnitList",
        )
        if any(price_row.get(key) for key in complex_list_keys):
            return "UNSUPPORTED_RATING_COMPLEX"

        free_value = price_row.get("freeValue")
        if free_value not in (None, "", 0, 0.0, "0", "0.0"):
            return "UNSUPPORTED_RATING_CONDITION"

        condition_price = price_row.get("conditionPrice")
        if condition_price not in (None, "", 0, 0.0, "0", "0.0"):
            base_price = self.get_price(price_row)
            condition_price_value = self.to_float(condition_price)
            tolerance = max(
                1e-9,
                abs(base_price) * 1e-12,
            )
            if abs(condition_price_value - base_price) > tolerance:
                return "UNSUPPORTED_RATING_CONDITION"

        return None

    def get_price_type_code(
        self,
        price_row: Dict[str, Any],
    ) -> str:
        price_type = price_row.get("priceType")
        price_type_mapping = self.as_dict(price_type)
        return str(
            self.first_present(
                price_type_mapping.get("code"),
                (
                    price_type
                    if isinstance(price_type, str)
                    else None
                ),
                price_row.get("priceTypeCode"),
                default="",
            )
        ).strip().upper()

    def resolve_unit_price(
        self,
        usage_unit_code: str,
        price_unit_type: str,
        price: float,
        days_in_month: int,
    ) -> Tuple[float, str, str]:
        hours_in_month = days_in_month * 24

        if usage_unit_code == "HOUR" and price_unit_type in ("USAGE_MM", "MONTH", "MONTHLY", "MONT", "MM"):
            return price / hours_in_month, "HOUR * (MONTH_PRICE / MONTH_HOURS)", "OK"

        if usage_unit_code == "HOUR" and price_unit_type in ("USAGE_HH", "HOUR", "HOURLY", "HH"):
            return price, "HOUR * HOUR_PRICE", "OK"

        if usage_unit_code == "HOUR" and price_unit_type in ("DAY", "DAILY", "DD"):
            return price / 24, "HOUR * (DAY_PRICE / 24)", "OK"

        if usage_unit_code == "HOUR" and price_unit_type == "STRG_1G_HH":
            return price, "HOUR * GB_HOUR_PRICE", "OK"

        if usage_unit_code == "HOUR" and price_unit_type == "STRG_1G_MM":
            return price / hours_in_month, "HOUR * (GB_MONTH_PRICE / MONTH_HOURS)", "OK"

        if usage_unit_code == "GBYTE_PER_MONTH_DAY" and price_unit_type in (
            "MMLY_AVG_SAVE_CAP_1G",
            "AVG_SAVE_CAP_1G",
            "STRG_1G_MM",
        ):
            return price, "GB_MONTH_USAGE * GB_MONTH_PRICE", "OK"

        if usage_unit_code == "GBYTE" and price_unit_type in ("USAGE_1GB", "GB", "GBYTE"):
            return price, "GB * GB_PRICE", "OK"

        if usage_unit_code in ("COUNT_CASE", "REQ_CNT") and price_unit_type in ("REQ_CNT", "COUNT_CASE"):
            return price, "COUNT * COUNT_PRICE", "OK"

        if usage_unit_code == "TOKEN" and price_unit_type in ("REQ_CNT", "TOKEN"):
            return price, "TOKEN * TOKEN_PRICE", "OK"

        if usage_unit_code == "TOKEN" and price_unit_type in ("K_TOKEN", "TOKEN_1000", "1000_TOKEN"):
            return price / 1000, "TOKEN * (PRICE / 1000)", "OK"

        if usage_unit_code == "TOKEN" and price_unit_type in ("M_TOKEN", "TOKEN_1000000", "1000000_TOKEN"):
            return price / 1_000_000, "TOKEN * (PRICE / 1000000)", "OK"

        return price, "USAGE * RAW_PRICE", "FALLBACK"

    def get_billing_multiplier(self, service_name: str, item_name: str) -> float:
        text = f"{service_name} {item_name}"

        if "Cloud DB for PostgreSQL" in text and "Primary & Secondary" in text:
            return 2.0

        return 1.0

    def summarize_expected_by_service(
        self,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        summary = defaultdict(lambda: {"expected_amount": 0.0, "row_count": 0})

        for row in rows:
            service_name = row["service_name"]
            summary[service_name]["expected_amount"] += self.to_float(row.get("expected_amount"))
            summary[service_name]["row_count"] += row.get("row_count", 0)

        return self.as_sorted_rows(summary, "service_name", "expected_amount")

    def compare_confirmed_and_expected(
        self,
        confirmed_summary: List[Dict[str, Any]],
        expected_summary: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        confirmed_map = {
            row["service_name"]: row
            for row in confirmed_summary
        }

        expected_map = {
            row["service_name"]: row
            for row in expected_summary
        }

        service_names = sorted(set(confirmed_map) | set(expected_map))
        result = []

        for service_name in service_names:
            confirmed_row = confirmed_map.get(service_name, {})
            confirmed = self.to_float(confirmed_row.get("amount"))
            comparison_base = self.to_float(
                self.first_present(
                    confirmed_row.get("use_amount"),
                    confirmed_row.get("amount"),
                    default=0,
                )
            )
            expected = self.to_float(expected_map.get(service_name, {}).get("expected_amount"))
            diff = expected - comparison_base

            result.append(
                {
                    "service_name": service_name,
                    "confirmed_amount": round(confirmed, 2),
                    "confirmed_use_amount": round(comparison_base, 2),
                    "comparison_base_amount": round(comparison_base, 2),
                    "comparison_basis": "PRE_DISCOUNT_USE_AMOUNT",
                    "expected_amount": round(expected, 2),
                    "diff_amount": round(diff, 2),
                    "diff_rate": self.safe_rate(diff, comparison_base),
                }
            )

        return sorted(result, key=lambda x: abs(x["diff_amount"]), reverse=True)

    def extract_rows(
        self,
        raw_pages: Any,
        target_key: str,
    ) -> List[Dict[str, Any]]:
        rows = self.find_all_lists(raw_pages, target_key)
        return [row for row in rows if isinstance(row, dict)]

    def find_all_lists(
        self,
        value: Any,
        target_key: str,
    ) -> List[Any]:
        result = []

        if isinstance(value, dict):
            if isinstance(value.get(target_key), list):
                result.extend(value[target_key])

            for child in value.values():
                result.extend(self.find_all_lists(child, target_key))

        elif isinstance(value, list):
            for item in value:
                result.extend(self.find_all_lists(item, target_key))

        return result

    def build_price_map(
        self,
        price_rows: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        return {
            str(row.get("priceNo")): row
            for row in price_rows
            if row.get("priceNo")
        }

    def get_product_demand_service_name(self, row: Dict[str, Any]) -> str:
        product_demand_type = self.as_dict(row.get("productDemandType"))
        return (
            product_demand_type.get("codeName")
            or product_demand_type.get("code")
            or row.get("productItemKindName")
            or row.get("contractTypeName")
            or "UNKNOWN"
        )

    def get_usage_service_name(self, row: Dict[str, Any]) -> str:
        contract = self.as_dict(row.get("contract"))
        contract_type = self.as_dict(contract.get("contractType"))
        return (
            contract_type.get("codeName")
            or contract_type.get("code")
            or "UNKNOWN"
        )

    def get_usage_item_name(self, row: Dict[str, Any]) -> str:
        contract_product = self.as_dict(row.get("contractProduct"))
        usage = self.as_dict(row.get("usage"))
        rating_type = self.as_dict(contract_product.get("productRatingType"))
        metering_type = self.as_dict(usage.get("meteringType"))
        item_kind = self.as_dict(contract_product.get("productItemKind"))

        return (
            rating_type.get("codeName")
            or metering_type.get("codeName")
            or item_kind.get("codeName")
            or "UNKNOWN"
        )

    def get_usage_item_code(self, row: Dict[str, Any]) -> str:
        contract_product = self.as_dict(row.get("contractProduct"))
        usage = self.as_dict(row.get("usage"))
        rating_type = self.as_dict(contract_product.get("productRatingType"))
        metering_type = self.as_dict(usage.get("meteringType"))

        return (
            rating_type.get("code")
            or metering_type.get("code")
            or "UNKNOWN"
        )

    def get_usage_quantity(self, row: Dict[str, Any]) -> float:
        usage = self.as_dict(row.get("usage"))
        return self.to_float(
            self.first_present(
                usage.get("userUsageQuantity"),
                usage.get("usageQuantity"),
                default=0,
            )
        )

    def get_usage_unit_code(self, row: Dict[str, Any]) -> str:
        usage = self.as_dict(row.get("usage"))
        user_unit = self.as_dict(usage.get("userUnit"))
        unit = self.as_dict(usage.get("unit"))
        return (
            user_unit.get("code")
            or unit.get("code")
            or "UNKNOWN"
        )

    def get_usage_unit_name(self, row: Dict[str, Any]) -> str:
        usage = self.as_dict(row.get("usage"))
        user_unit = self.as_dict(usage.get("userUnit"))
        unit = self.as_dict(usage.get("unit"))
        return (
            user_unit.get("codeName")
            or unit.get("codeName")
            or self.get_usage_unit_code(row)
        )

    def get_price_no(self, row: Dict[str, Any]) -> str:
        return str(
            self.first_present(
                self.as_dict(row.get("contractProduct")).get("priceNo"),
                default="",
            )
        )

    def get_price(self, price_row: Dict[str, Any]) -> float:
        return self.to_float(
            self.first_present(
                price_row.get("price"),
                price_row.get("unitPrice"),
                price_row.get("meteringUnitPrice"),
                default=0,
            )
        )

    def get_price_unit_type_code(self, price_row: Dict[str, Any]) -> str:
        price_unit_type = self.as_dict(price_row.get("priceUnitType"))
        unit = self.as_dict(price_row.get("unit"))
        return (
            price_unit_type.get("code")
            or unit.get("code")
            or ""
        )

    def get_charging_unit_type_code(self, price_row: Dict[str, Any]) -> str:
        charging_unit_type = self.as_dict(price_row.get("chargingUnitType"))
        metering_unit = self.as_dict(price_row.get("meteringUnit"))
        return (
            charging_unit_type.get("code")
            or metering_unit.get("code")
            or ""
        )

    def get_storage_size_gb(self, row: Dict[str, Any]) -> float:
        contract_product = self.as_dict(row.get("contractProduct"))
        usage = self.as_dict(row.get("usage"))

        candidates = [
            contract_product.get("productSize"),
            contract_product.get("productSizeValue"),
            contract_product.get("storageSize"),
            contract_product.get("storageSizeGb"),
            contract_product.get("diskSize"),
            contract_product.get("diskSizeGb"),
            contract_product.get("blockStorageSize"),
            contract_product.get("blockStorageSizeGb"),
            usage.get("productSize"),
            usage.get("productSizeValue"),
            usage.get("storageSize"),
            usage.get("storageSizeGb"),
            usage.get("diskSize"),
            usage.get("diskSizeGb"),
            usage.get("blockStorageSize"),
            usage.get("blockStorageSizeGb"),
        ]

        for value in candidates:
            size = self.to_float(value)

            if size <= 0:
                continue

            if size >= 1024 ** 3:
                return size / (1024 ** 3)

            return size

        return 0.0

    def get_network_direction(self, name: str) -> str:
        text = (name or "").upper()

        if "INBOUND" in text or "NETWORK IN" in text:
            return "인바운드"

        if "OUTBOUND" in text or "NETWORK OUT" in text:
            return "아웃바운드"

        return "기타"

    def get_days_in_month(
        self,
        billing_month: str = None,
        use_end_date: str = None,
    ) -> int:
        value = billing_month or use_end_date

        if not value:
            return 31

        text = str(value).replace("-", "")

        try:
            year = int(text[:4])
            month = int(text[4:6])
            return calendar.monthrange(year, month)[1]
        except (TypeError, ValueError, IndexError):
            return 31

    def as_sorted_rows(
        self,
        summary: Dict[Any, Dict[str, Any]],
        key_name: str,
        amount_key: str,
    ) -> List[Dict[str, Any]]:
        rows = []

        for key, item in summary.items():
            row = {key_name: key}

            for item_key, value in item.items():
                if isinstance(value, float):
                    row[item_key] = round(value, 2)
                else:
                    row[item_key] = value

            rows.append(row)

        return sorted(rows, key=lambda x: x.get(amount_key, 0), reverse=True)

    def safe_rate(
        self,
        value: float,
        base: float,
    ) -> Optional[float]:
        if not base:
            return 0.0 if not value else None

        return round((value / base) * 100, 2)

    def to_float(self, value: Any) -> float:
        if value in (None, ""):
            return 0.0

        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return 0.0
