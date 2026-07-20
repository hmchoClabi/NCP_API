from collections import defaultdict
from typing import Any, Dict, List, Tuple
import calendar


class BillingNormalizer:
    def normalize(
        self,
        raw_data: Dict[str, Any],
        current_month: str = None,
        billing_month: str = None,
        use_end_date: str = None,
    ) -> Dict[str, Any]:

        billing_month = billing_month or current_month
        days_in_month = self.get_days_in_month(billing_month, use_end_date)

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

        expected_by_service = self.summarize_expected_by_service(expected_cost_summary)
        comparison_summary = self.compare_confirmed_and_expected(
            confirmed_summary=service_summary,
            expected_summary=expected_by_service,
        )

        confirmed_total = sum(row["amount"] for row in service_summary)
        expected_total = sum(row["expected_amount"] for row in expected_cost_summary)

        return {
            "summary": {
                "billing_month": billing_month,
                "days_in_month": days_in_month,
                "confirmed_total_amount": round(confirmed_total, 2),
                "expected_total_amount": round(expected_total, 2),
                "diff_amount": round(expected_total - confirmed_total, 2),
                "diff_rate": self.safe_rate(expected_total - confirmed_total, confirmed_total),
                "service_count": len(service_summary),
                "usage_summary_count": len(usage_summary),
                "network_usage_count": len(network_usage_summary),
                "expected_cost_count": len(expected_cost_summary),
                "discount_count": len(discount_rows),
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
        }

    def summarize_confirmed_by_service(
        self,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        summary = defaultdict(lambda: {"amount": 0.0, "use_amount": 0.0, "discount_amount": 0.0, "row_count": 0})

        for row in rows:
            service_name = self.get_product_demand_service_name(row)

            use_amount = self.to_float(row.get("useAmount"))
            demand_amount = self.to_float(row.get("demandAmount") or row.get("useAmount"))

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

            total_discount = promise + promotion + etc + product + credit

            summary[service_name]["use_amount"] += self.to_float(row.get("useAmount"))
            summary[service_name]["demand_amount"] += self.to_float(row.get("demandAmount"))
            summary[service_name]["total_discount_amount"] += total_discount
            summary[service_name]["promise_discount_amount"] += promise
            summary[service_name]["promotion_discount_amount"] += promotion
            summary[service_name]["etc_discount_amount"] += etc
            summary[service_name]["product_discount_amount"] += product
            summary[service_name]["credit_discount_amount"] += credit
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

    # def summarize_network_usage(
    #     self,
    #     rows: List[Dict[str, Any]],
    # ) -> List[Dict[str, Any]]:
    #     summary = defaultdict(lambda: {"usage_gb": 0.0, "row_count": 0})

    #     for row in rows:
    #         unit_code = self.get_usage_unit_code(row)
    #         if unit_code != "GBYTE":
    #             continue

    #         item_name = self.get_usage_item_name(row)
    #         direction = self.get_network_direction(item_name)

    #         if direction != "아웃바운드":
    #             continue

    #         service_name = self.get_usage_service_name(row)
    #         key = (service_name, item_name)

    #         summary[key]["usage_gb"] += self.get_usage_quantity(row)
    #         summary[key]["row_count"] += 1

    #     result = []

    #     for key, item in summary.items():
    #         service_name, item_name = key
    #         result.append(
    #             {
    #                 "service_name": service_name,
    #                 "direction": "아웃바운드",
    #                 "name": item_name,
    #                 "usage_gb": round(item["usage_gb"], 3),
    #                 "row_count": item["row_count"],
    #             }
    #         )

    #     return sorted(result, key=lambda x: (x["service_name"], x["name"]))

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

            if not price_row:
                continue

            service_name = self.get_usage_service_name(row)
            item_name = self.get_usage_item_name(row)
            item_code = self.get_usage_item_code(row)
            unit_code = self.get_usage_unit_code(row)
            usage_quantity = self.get_usage_quantity(row)

            calculated = self.calculate_expected_amount(
                row=row,
                price_row=price_row,
                usage_quantity=usage_quantity,
                usage_unit_code=unit_code,
                days_in_month=days_in_month,
            )

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
            summary[key]["raw_price"] = self.get_price(price_row)
            summary[key]["storage_size_gb"] = self.get_storage_size_gb(row)
            summary[key]["price_unit_type"] = self.get_price_unit_type_code(price_row)
            summary[key]["charging_unit_type"] = self.get_charging_unit_type_code(price_row)
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
        price_unit_type = self.get_price_unit_type_code(price_row)
        storage_size_gb = self.get_storage_size_gb(row)
        hours_in_month = days_in_month * 24

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

        if price_unit_type in ("STRG_1G_HH", "STRG_1G_MM"):
            if storage_size_gb > 0:
                amount = storage_size_gb * usage_quantity * unit_price
                method = f"GB * {method}"
                status = "OK"
            else:
                status = "WARN_STORAGE_SIZE_MISSING"

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
            confirmed = self.to_float(confirmed_map.get(service_name, {}).get("amount"))
            expected = self.to_float(expected_map.get(service_name, {}).get("expected_amount"))
            diff = expected - confirmed

            result.append(
                {
                    "service_name": service_name,
                    "confirmed_amount": round(confirmed, 2),
                    "expected_amount": round(expected, 2),
                    "diff_amount": round(diff, 2),
                    "diff_rate": self.safe_rate(diff, confirmed),
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
        return (
            row.get("productDemandType", {}).get("codeName")
            or row.get("productDemandType", {}).get("code")
            or row.get("productItemKindName")
            or row.get("contractTypeName")
            or "UNKNOWN"
        )

    def get_usage_service_name(self, row: Dict[str, Any]) -> str:
        contract = row.get("contract", {})
        return (
            contract.get("contractType", {}).get("codeName")
            or contract.get("contractType", {}).get("code")
            or "UNKNOWN"
        )

    def get_usage_item_name(self, row: Dict[str, Any]) -> str:
        contract_product = row.get("contractProduct", {})
        usage = row.get("usage", {})

        return (
            contract_product.get("productRatingType", {}).get("codeName")
            or usage.get("meteringType", {}).get("codeName")
            or contract_product.get("productItemKind", {}).get("codeName")
            or "UNKNOWN"
        )

    def get_usage_item_code(self, row: Dict[str, Any]) -> str:
        contract_product = row.get("contractProduct", {})
        usage = row.get("usage", {})

        return (
            contract_product.get("productRatingType", {}).get("code")
            or usage.get("meteringType", {}).get("code")
            or "UNKNOWN"
        )

    def get_usage_quantity(self, row: Dict[str, Any]) -> float:
        usage = row.get("usage", {})
        return self.to_float(
            usage.get("userUsageQuantity")
            or usage.get("usageQuantity")
            or 0
        )

    def get_usage_unit_code(self, row: Dict[str, Any]) -> str:
        usage = row.get("usage", {})
        return (
            usage.get("userUnit", {}).get("code")
            or usage.get("unit", {}).get("code")
            or "UNKNOWN"
        )

    def get_usage_unit_name(self, row: Dict[str, Any]) -> str:
        usage = row.get("usage", {})
        return (
            usage.get("userUnit", {}).get("codeName")
            or usage.get("unit", {}).get("codeName")
            or self.get_usage_unit_code(row)
        )

    def get_price_no(self, row: Dict[str, Any]) -> str:
        return str(row.get("contractProduct", {}).get("priceNo") or "")

    def get_price(self, price_row: Dict[str, Any]) -> float:
        return self.to_float(
            price_row.get("price")
            or price_row.get("unitPrice")
            or price_row.get("meteringUnitPrice")
            or 0
        )

    def get_price_unit_type_code(self, price_row: Dict[str, Any]) -> str:
        return (
            price_row.get("priceUnitType", {}).get("code")
            or price_row.get("unit", {}).get("code")
            or ""
        )

    def get_charging_unit_type_code(self, price_row: Dict[str, Any]) -> str:
        return (
            price_row.get("chargingUnitType", {}).get("code")
            or price_row.get("meteringUnit", {}).get("code")
            or ""
        )

    def get_storage_size_gb(self, row: Dict[str, Any]) -> float:
        contract_product = row.get("contractProduct", {})
        usage = row.get("usage", {})

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

        if "OUTBOUND" in text or "NETWORK OUT" in text or "OUT" in text:
            return "아웃바운드"

        if "INBOUND" in text or "NETWORK IN" in text:
            return "인바운드"

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
        except Exception:
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
    ) -> float:
        if not base:
            return 0.0

        return round((value / base) * 100, 2)

    def to_float(self, value: Any) -> float:
        if value in (None, ""):
            return 0.0

        try:
            return float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return 0.0
# from typing import Any, Dict, List
# import calendar


# class BillingNormalizer:

#     def normalize(self, raw_data, current_month=None, billing_month=None, use_end_date=None):
#         billing_month = billing_month or current_month

#         demand_rows = self.extract_rows(raw_data.get("demand_cost", []), "productDemandCostList")
#         daily_usage_rows = self.extract_rows(raw_data.get("daily_usage", []), "contractUsageListByDaily")
#         price_rows = self.extract_rows(
#             raw_data.get("daily_price_list", []) or raw_data.get("price_list", []),
#             "priceList",
#         )

#         days_in_month = self.get_days_in_month(billing_month=billing_month, use_end_date=use_end_date)

#         service_summary = self.summarize_by_service(demand_rows)
#         usage_summary = self.summarize_usage_by_service(daily_usage_rows)
#         network_usage_summary = self.summarize_network_usage(daily_usage_rows)
#         expected_cost_summary = self.summarize_expected_cost(
#             usage_rows=daily_usage_rows,
#             price_rows=price_rows,
#             days_in_month=days_in_month,
#         )

#         confirmed_total = self.calculate_total_amount(demand_rows)
#         expected_total = sum(item["expected_amount"] for item in expected_cost_summary)

#         return {
#             "summary": {
#                 "billing_month": billing_month,
#                 "days_in_month": days_in_month,
#                 "confirmed_total_amount": round(confirmed_total, 2),
#                 "expected_total_amount": round(expected_total, 2),
#                 "diff_amount": round(expected_total - confirmed_total, 2),
#                 "service_count": len(service_summary),
#                 "row_count": len(demand_rows),
#                 "daily_usage_row_count": len(daily_usage_rows),
#                 "price_row_count": len(price_rows),
#                 "usage_summary_count": len(usage_summary),
#                 "network_usage_count": len(network_usage_summary),
#                 "expected_cost_count": len(expected_cost_summary),
#             },
#             "service_summary": service_summary,
#             "usage_summary": usage_summary,
#             "network_usage_summary": network_usage_summary,
#             "expected_cost_summary": expected_cost_summary,
#             "demand_cost_rows": demand_rows,
#             "daily_usage_rows": daily_usage_rows,
#             "price_rows": price_rows,
#         }

#     def extract_rows(self, raw_pages: List[Dict[str, Any]], target_key: str) -> List[Dict[str, Any]]:
#         rows = []

#         for page in raw_pages:
#             items = self.find_first_list(page.get("response"), target_key)
#             rows.extend(item for item in items if isinstance(item, dict))

#         return rows

#     def calculate_total_amount(self, rows: List[Dict[str, Any]]) -> float:
#         return sum(
#             self.to_float(row.get("demandAmount") or row.get("useAmount") or 0)
#             for row in rows
#         )

#     def summarize_by_service(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
#         summary = {}

#         for row in rows:
#             service_name = (
#                 row.get("productDemandType", {}).get("codeName")
#                 or row.get("productItemKindName")
#                 or row.get("contractTypeName")
#                 or "UNKNOWN"
#             )

#             amount = self.to_float(row.get("demandAmount") or row.get("useAmount") or 0)

#             if service_name not in summary:
#                 summary[service_name] = {
#                     "service_name": service_name,
#                     "amount": 0.0,
#                     "row_count": 0,
#                 }

#             summary[service_name]["amount"] += amount
#             summary[service_name]["row_count"] += 1

#         return sorted(
#             [
#                 {
#                     "service_name": item["service_name"],
#                     "amount": round(item["amount"], 2),
#                     "row_count": item["row_count"],
#                 }
#                 for item in summary.values()
#             ],
#             key=lambda x: x["amount"],
#             reverse=True,
#         )

#     def summarize_usage_by_service(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
#         summary = {}

#         for row in rows:
#             service_name = self.get_service_name(row)
#             item_name = self.get_item_name(row)
#             item_code = self.get_item_code(row)
#             usage_quantity = self.get_usage_quantity(row)
#             unit_code = self.get_unit_code(row)
#             unit_name = self.get_unit_name(row)

#             key = (service_name, item_name, item_code, unit_code)

#             if key not in summary:
#                 summary[key] = {
#                     "service_name": service_name,
#                     "item_name": item_name,
#                     "item_code": item_code,
#                     "usage_quantity": 0.0,
#                     "unit_code": unit_code,
#                     "unit_name": unit_name,
#                     "row_count": 0,
#                 }

#             summary[key]["usage_quantity"] += usage_quantity
#             summary[key]["row_count"] += 1

#         return sorted(
#             [
#                 {
#                     "service_name": item["service_name"],
#                     "item_name": item["item_name"],
#                     "item_code": item["item_code"],
#                     "usage_quantity": round(item["usage_quantity"], 6),
#                     "unit_code": item["unit_code"],
#                     "unit_name": item["unit_name"],
#                     "row_count": item["row_count"],
#                 }
#                 for item in summary.values()
#                 if item["usage_quantity"] != 0
#             ],
#             key=lambda x: (x["service_name"], x["item_name"]),
#         )

#     def summarize_network_usage(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
#         summary = {}

#         for row in rows:
#             if self.get_product_item_kind_code(row) != "NET":
#                 continue

#             unit_code = self.get_unit_code(row)

#             if unit_code != "GBYTE":
#                 continue

#             item_name = self.get_item_name(row)
#             direction = self.get_network_direction(item_name)

#             if direction != "아웃바운드":
#                 continue

#             service_name = self.get_service_name(row)
#             item_code = self.get_item_code(row)
#             usage_gb = self.get_usage_quantity(row)

#             key = (service_name, direction, item_name)

#             if key not in summary:
#                 summary[key] = {
#                     "service_name": service_name,
#                     "direction": direction,
#                     "name": item_name,
#                     "code": item_code,
#                     "usage_gb": 0.0,
#                     "row_count": 0,
#                     "unit_codes": set(),
#                 }

#             summary[key]["usage_gb"] += usage_gb
#             summary[key]["row_count"] += 1
#             summary[key]["unit_codes"].add(unit_code)

#         return sorted(
#             [
#                 {
#                     "service_name": item["service_name"],
#                     "direction": item["direction"],
#                     "name": item["name"],
#                     "code": item["code"],
#                     "usage_gb": round(item["usage_gb"], 3),
#                     "row_count": item["row_count"],
#                     "unit_codes": sorted(item["unit_codes"]),
#                 }
#                 for item in summary.values()
#             ],
#             key=lambda x: (x["service_name"], x["name"]),
#         )

#     def summarize_expected_cost(
#         self,
#         usage_rows: List[Dict[str, Any]],
#         price_rows: List[Dict[str, Any]],
#         days_in_month: int,
#     ) -> List[Dict[str, Any]]:
#         price_map = self.build_price_map(price_rows)
#         summary = {}

#         for row in usage_rows:
#             price_no = self.get_price_no(row)
#             price_row = price_map.get(price_no)

#             if not price_row:
#                 continue

#             service_name = self.get_service_name(row)
#             item_name = self.get_item_name(row)
#             item_code = self.get_item_code(row)
#             unit_code = self.get_unit_code(row)
#             usage_quantity = self.get_usage_quantity(row)

#             raw_price = self.get_price(price_row)
#             price_unit_type = self.get_price_unit_type_code(price_row)
#             charging_unit_type = self.get_charging_unit_type_code(price_row)
#             storage_size_gb = self.get_storage_size_gb(row)

#             expected_amount, unit_price, calculation_method, calculation_status = (
#                 self.calculate_expected_amount(
#                     row=row,
#                     price_row=price_row,
#                     usage_quantity=usage_quantity,
#                     usage_unit_code=unit_code,
#                     days_in_month=days_in_month,
#                 )
#             )

#             key = (
#                 service_name,
#                 item_name,
#                 item_code,
#                 unit_code,
#                 price_no,
#                 calculation_method,
#                 calculation_status,
#             )

#             if key not in summary:
#                 summary[key] = {
#                     "service_name": service_name,
#                     "item_name": item_name,
#                     "item_code": item_code,
#                     "price_no": price_no,
#                     "usage_quantity": 0.0,
#                     "unit_code": unit_code,
#                     "raw_price": raw_price,
#                     "price_unit_type": price_unit_type,
#                     "charging_unit_type": charging_unit_type,
#                     "unit_price": unit_price,
#                     "storage_size_gb": storage_size_gb,
#                     "expected_amount": 0.0,
#                     "row_count": 0,
#                     "calculation_method": calculation_method,
#                     "calculation_status": calculation_status,
#                 }

#             summary[key]["usage_quantity"] += usage_quantity
#             summary[key]["expected_amount"] += expected_amount
#             summary[key]["row_count"] += 1

#         return sorted(
#             [
#                 {
#                     "service_name": item["service_name"],
#                     "item_name": item["item_name"],
#                     "item_code": item["item_code"],
#                     "price_no": item["price_no"],
#                     "usage_quantity": round(item["usage_quantity"], 6),
#                     "unit_code": item["unit_code"],
#                     "raw_price": round(item["raw_price"], 10),
#                     "price_unit_type": item["price_unit_type"],
#                     "charging_unit_type": item["charging_unit_type"],
#                     "unit_price": round(item["unit_price"], 10),
#                     "storage_size_gb": round(item["storage_size_gb"], 6),
#                     "expected_amount": round(item["expected_amount"], 2),
#                     "row_count": item["row_count"],
#                     "calculation_method": item["calculation_method"],
#                     "calculation_status": item["calculation_status"],
#                 }
#                 for item in summary.values()
#                 if item["usage_quantity"] != 0 or item["expected_amount"] != 0
#             ],
#             key=lambda x: x["expected_amount"],
#             reverse=True,
#         )

#     def calculate_expected_amount(
#         self,
#         row: Dict[str, Any],
#         price_row: Dict[str, Any],
#         usage_quantity: float,
#         usage_unit_code: str,
#         days_in_month: int,
#     ):
#         price = self.get_price(price_row)
#         price_unit_type = self.get_price_unit_type_code(price_row)
#         storage_size_gb = self.get_storage_size_gb(row)
#         hours_in_month = days_in_month * 24

#         if usage_unit_code == "HOUR" and price_unit_type == "USAGE_MM":
#             unit_price = price / hours_in_month
#             return (
#                 usage_quantity * unit_price,
#                 unit_price,
#                 "HOUR * (MONTH_PRICE / MONTH_HOURS)",
#                 "OK",
#             )

#         if usage_unit_code == "HOUR" and price_unit_type == "USAGE_HH":
#             return (
#                 usage_quantity * price,
#                 price,
#                 "HOUR * HOUR_PRICE",
#                 "OK",
#             )

#         if usage_unit_code == "HOUR" and price_unit_type == "STRG_1G_HH":
#             if storage_size_gb > 0:
#                 return (
#                     storage_size_gb * usage_quantity * price,
#                     price,
#                     "GB * HOUR * GB_HOUR_PRICE",
#                     "OK",
#                 )

#             return (
#                 usage_quantity * price,
#                 price,
#                 "HOUR * GB_HOUR_PRICE",
#                 "WARN_STORAGE_SIZE_MISSING",
#             )

#         if usage_unit_code == "HOUR" and price_unit_type == "STRG_1G_MM":
#             if storage_size_gb > 0:
#                 unit_price = price / hours_in_month
#                 return (
#                     storage_size_gb * usage_quantity * unit_price,
#                     unit_price,
#                     "GB * HOUR * (GB_MONTH_PRICE / MONTH_HOURS)",
#                     "OK",
#                 )

#             unit_price = price / hours_in_month
#             return (
#                 usage_quantity * unit_price,
#                 unit_price,
#                 "HOUR * (GB_MONTH_PRICE / MONTH_HOURS)",
#                 "WARN_STORAGE_SIZE_MISSING",
#             )

#         if usage_unit_code == "GBYTE_PER_MONTH_DAY" and price_unit_type in (
#             "MMLY_AVG_SAVE_CAP_1G",
#             "AVG_SAVE_CAP_1G",
#             "STRG_1G_MM",
#         ):
#             return (
#                 usage_quantity * price,
#                 price,
#                 "GB_MONTH_USAGE * GB_MONTH_PRICE",
#                 "OK",
#             )

#         if usage_unit_code == "GBYTE" and price_unit_type == "USAGE_1GB":
#             return (
#                 usage_quantity * price,
#                 price,
#                 "GB * GB_PRICE",
#                 "OK",
#             )

#         if usage_unit_code in ("COUNT_CASE", "REQ_CNT") and price_unit_type in ("REQ_CNT", "COUNT_CASE"):
#             return (
#                 usage_quantity * price,
#                 price,
#                 "COUNT * COUNT_PRICE",
#                 "OK",
#             )

#         if usage_unit_code == "TOKEN" and price_unit_type in ("REQ_CNT", "TOKEN"):
#             return (
#                 usage_quantity * price,
#                 price,
#                 "TOKEN * TOKEN_PRICE",
#                 "OK",
#             )

#         if usage_unit_code == "TOKEN" and price_unit_type in ("K_TOKEN", "TOKEN_1000", "1000_TOKEN"):
#             unit_price = price / 1000
#             return (
#                 usage_quantity * unit_price,
#                 unit_price,
#                 "TOKEN * (PRICE / 1000)",
#                 "OK",
#             )

#         if usage_unit_code == "TOKEN" and price_unit_type in ("M_TOKEN", "TOKEN_1000000", "1000000_TOKEN"):
#             unit_price = price / 1_000_000
#             return (
#                 usage_quantity * unit_price,
#                 unit_price,
#                 "TOKEN * (PRICE / 1000000)",
#                 "OK",
#             )

#         unit_price = self.get_effective_unit_price(
#             price_row=price_row,
#             usage_unit_code=usage_unit_code,
#             days_in_month=days_in_month,
#         )

#         return (
#             usage_quantity * unit_price,
#             unit_price,
#             "USAGE * EFFECTIVE_PRICE",
#             "FALLBACK",
#         )

#     def build_price_map(self, price_rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
#         result = {}

#         for row in price_rows:
#             price_no = str(row.get("priceNo") or "")
#             if price_no:
#                 result[price_no] = row

#         return result

#     def get_price_no(self, row: Dict[str, Any]) -> str:
#         return str(row.get("contractProduct", {}).get("priceNo") or "")

#     def get_service_name(self, row: Dict[str, Any]) -> str:
#         contract = row.get("contract", {})
#         return (
#             contract.get("contractType", {}).get("codeName")
#             or contract.get("contractType", {}).get("code")
#             or "UNKNOWN"
#         )

#     def get_product_item_kind_code(self, row: Dict[str, Any]) -> str:
#         return (
#             row.get("contractProduct", {})
#             .get("productItemKind", {})
#             .get("code")
#             or "UNKNOWN"
#         )

#     def get_item_name(self, row: Dict[str, Any]) -> str:
#         contract_product = row.get("contractProduct", {})
#         usage = row.get("usage", {})

#         return (
#             contract_product.get("productRatingType", {}).get("codeName")
#             or usage.get("meteringType", {}).get("codeName")
#             or contract_product.get("productItemKind", {}).get("codeName")
#             or "UNKNOWN"
#         )

#     def get_item_code(self, row: Dict[str, Any]) -> str:
#         contract_product = row.get("contractProduct", {})
#         usage = row.get("usage", {})

#         return (
#             contract_product.get("productRatingType", {}).get("code")
#             or usage.get("meteringType", {}).get("code")
#             or "UNKNOWN"
#         )

#     def get_usage_quantity(self, row: Dict[str, Any]) -> float:
#         usage = row.get("usage", {})
#         return self.to_float(
#             usage.get("userUsageQuantity")
#             or usage.get("usageQuantity")
#             or 0
#         )

#     def get_unit_code(self, row: Dict[str, Any]) -> str:
#         usage = row.get("usage", {})
#         return (
#             usage.get("userUnit", {}).get("code")
#             or usage.get("unit", {}).get("code")
#             or "UNKNOWN"
#         )

#     def get_unit_name(self, row: Dict[str, Any]) -> str:
#         usage = row.get("usage", {})
#         return (
#             usage.get("userUnit", {}).get("codeName")
#             or usage.get("unit", {}).get("codeName")
#             or self.get_unit_code(row)
#         )

#     def get_storage_size_gb(self, row: Dict[str, Any]) -> float:
#         contract_product = row.get("contractProduct", {})
#         usage = row.get("usage", {})

#         candidates = [
#             contract_product.get("productSize"),
#             contract_product.get("productSizeValue"),
#             contract_product.get("storageSize"),
#             contract_product.get("storageSizeGb"),
#             contract_product.get("diskSize"),
#             contract_product.get("diskSizeGb"),
#             contract_product.get("blockStorageSize"),
#             contract_product.get("blockStorageSizeGb"),
#             usage.get("productSize"),
#             usage.get("productSizeValue"),
#             usage.get("storageSize"),
#             usage.get("storageSizeGb"),
#             usage.get("diskSize"),
#             usage.get("diskSizeGb"),
#             usage.get("blockStorageSize"),
#             usage.get("blockStorageSizeGb"),
#         ]

#         for value in candidates:
#             size = self.to_float(value)

#             if size <= 0:
#                 continue

#             # NCP raw에 10737418240처럼 byte 단위로 들어오는 경우가 있음.
#             # 10GB = 10 * 1024^3 = 10737418240
#             if size >= 1024 ** 3:
#                 return size / (1024 ** 3)

#             # 이미 GB 단위로 들어온 경우
#             return size

#         return 0.0

#     def get_price(self, price_row: Dict[str, Any]) -> float:
#         return self.to_float(
#             price_row.get("price")
#             or price_row.get("unitPrice")
#             or price_row.get("meteringUnitPrice")
#             or 0
#         )

#     def get_price_unit_type_code(self, price_row: Dict[str, Any]) -> str:
#         return (
#             price_row.get("priceUnitType", {}).get("code")
#             or price_row.get("unit", {}).get("code")
#             or ""
#         )

#     def get_charging_unit_type_code(self, price_row: Dict[str, Any]) -> str:
#         return (
#             price_row.get("chargingUnitType", {}).get("code")
#             or price_row.get("meteringUnit", {}).get("code")
#             or ""
#         )

#     def get_effective_unit_price(
#         self,
#         price_row: Dict[str, Any],
#         usage_unit_code: str,
#         days_in_month: int,
#     ) -> float:
#         price = self.get_price(price_row)
#         price_unit_type = self.get_price_unit_type_code(price_row)
#         hours_in_month = days_in_month * 24

#         if usage_unit_code == "HOUR" and price_unit_type in ("USAGE_MM", "MONTH", "MONTHLY", "MONT", "MM"):
#             return price / hours_in_month

#         if usage_unit_code == "HOUR" and price_unit_type in ("USAGE_HH", "HOUR", "HOURLY", "HH"):
#             return price

#         if usage_unit_code == "HOUR" and price_unit_type in ("DAY", "DAILY", "DD"):
#             return price / 24

#         if usage_unit_code == "GBYTE_PER_MONTH_DAY" and price_unit_type in (
#             "MMLY_AVG_SAVE_CAP_1G",
#             "AVG_SAVE_CAP_1G",
#             "STRG_1G_MM",
#         ):
#             return price

#         if usage_unit_code == "GBYTE" and price_unit_type in ("USAGE_1GB", "GB", "GBYTE"):
#             return price

#         if usage_unit_code in ("COUNT_CASE", "REQ_CNT") and price_unit_type in ("REQ_CNT", "COUNT_CASE"):
#             return price

#         if usage_unit_code == "TOKEN" and price_unit_type in ("REQ_CNT", "TOKEN"):
#             return price

#         return price

#     def get_days_in_month(self, billing_month=None, use_end_date=None) -> int:
#         value = billing_month or use_end_date

#         if not value:
#             return 31

#         text = str(value)

#         try:
#             year = int(text[:4])
#             month = int(text[4:6])
#             return calendar.monthrange(year, month)[1]
#         except Exception:
#             return 31

#     def get_network_direction(self, name: str) -> str:
#         name_upper = (name or "").upper()

#         if "IN" in name_upper and "OUT" not in name_upper:
#             return "인바운드"

#         if "OUT" in name_upper or "OUTBOUND" in name_upper:
#             return "아웃바운드"

#         return "기타"

#     def find_first_list(self, value: Any, target_key: str) -> List[Any]:
#         if isinstance(value, dict):
#             if isinstance(value.get(target_key), list):
#                 return value[target_key]

#             for child in value.values():
#                 found = self.find_first_list(child, target_key)
#                 if found:
#                     return found

#         elif isinstance(value, list):
#             for item in value:
#                 found = self.find_first_list(item, target_key)
#                 if found:
#                     return found

#         return []

#     def to_float(self, value: Any) -> float:
#         if value in (None, ""):
#             return 0.0

#         try:
#             return float(str(value).replace(",", ""))
#         except (TypeError, ValueError):
#             return 0.0