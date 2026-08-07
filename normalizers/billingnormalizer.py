from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple
import calendar
from datetime import date, datetime, timedelta


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
        report_period: Optional[Dict[str, Any]] = None,
        calculated_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        billing_month = billing_month or current_month
        report_period = report_period or {}
        days_in_month = self.get_days_in_month(billing_month, use_end_date)
        raw_meta = self.as_dict(raw_data.get("_meta"))
        collection_errors = self._dict_list(raw_meta.get("collection_errors"))
        collection_warnings = self._dict_list(raw_meta.get("collection_warnings"))
        comparison_input_errors = [
            error for error in collection_errors
            if error.get("comparison_required")
        ]

        demand_rows = self.extract_rows(
            raw_data.get("product_demand_cost", []), "productDemandCostList"
        )
        confirmed_demand_rows = self.extract_rows(
            raw_data.get("confirmed_demand_cost", []), "demandCostList"
        )
        confirmed_product_rows = self.extract_rows(
            raw_data.get("confirmed_product_demand_cost", []),
            "productDemandCostList",
        ) or demand_rows
        demand_discount_rows = self.extract_rows(
            raw_data.get("product_demand_cost_by_discount", []),
            "productDemandCostByDiscountList",
        )
        daily_usage_rows = self.extract_rows(
            raw_data.get("daily_usage", []), "contractUsageListByDaily"
        )
        month_to_date_usage_rows = self.extract_rows(
            raw_data.get("month_to_date_usage", []),
            "contractUsageListByDaily",
        )
        price_rows = self.extract_rows(raw_data.get("price_list", []), "priceList")
        discount_rows = self.extract_rows(
            raw_data.get("discount_list", []), "discountList"
        )

        service_summary = self.summarize_confirmed_by_service(
            confirmed_product_rows
        )
        target_service_summary = self.summarize_confirmed_by_service(demand_rows)
        discount_summary = self.summarize_discount_by_service(demand_discount_rows)
        usage_summary = self.summarize_usage(daily_usage_rows)
        network_usage_summary = self.summarize_network_usage(daily_usage_rows)
        expected_cost_summary = self.summarize_expected_cost(
            usage_rows=daily_usage_rows,
            price_rows=price_rows,
            days_in_month=days_in_month,
        )
        month_to_date_cost_summary = self.summarize_expected_cost(
            usage_rows=month_to_date_usage_rows,
            price_rows=price_rows,
            days_in_month=days_in_month,
        )

        verified_expected_rows = self._verified_cost_rows(expected_cost_summary)
        expected_by_service = self.summarize_expected_by_service(
            verified_expected_rows
        )
        confirmed_use_total = sum(
            row["use_amount"] for row in target_service_summary
        )
        expected_total = sum(row["expected_amount"] for row in verified_expected_rows)
        expected_total_all = sum(
            row["expected_amount"] for row in expected_cost_summary
        )
        unverified_expected_amount = expected_total_all - expected_total
        calculation_status_counts = dict(Counter(
            row.get("calculation_status") or "UNKNOWN"
            for row in expected_cost_summary
        ))
        has_unverified_expected = any(
            status != "OK" for status in calculation_status_counts
        )
        if comparison_enabled and not expected_cost_summary and confirmed_use_total != 0:
            has_unverified_expected = True

        if not comparison_enabled:
            comparison_status = "SKIPPED_DIFFERENT_PERIOD_SCOPE"
        elif comparison_input_errors:
            comparison_status = "PARTIAL_BILLING_COLLECTION_ERROR"
        elif has_unverified_expected:
            comparison_status = "PARTIAL_UNVERIFIED_EXPECTED_COST"
        else:
            comparison_status = "OK"

        comparison_summary = (
            self.compare_confirmed_and_expected(
                confirmed_summary=target_service_summary,
                expected_summary=expected_by_service,
            )
            if comparison_status == "OK" else []
        )
        diff_amount: Optional[float] = None
        diff_rate: Optional[float] = None
        if comparison_status == "OK":
            diff_amount = round(expected_total - confirmed_use_total, 2)
            diff_rate = self.safe_rate(diff_amount, confirmed_use_total)

        confirmed_month = str(
            raw_meta.get("confirmed_demand_month")
            or report_period.get("confirmed_demand_month")
            or billing_month
        )
        invoice_summary = self.summarize_confirmed_invoice(
            confirmed_demand_rows, confirmed_month, calculated_at
        )
        requested_start, requested_end = self.report_period_dates(
            report_period, billing_month
        )
        period_estimate = self.build_estimate_fact(
            "PERIOD_ESTIMATE", requested_start, requested_end,
            self.usage_coverage(daily_usage_rows), expected_cost_summary,
            calculated_at,
        )
        month_to_date_start = (
            self._parse_api_date(report_period.get("month_to_date_start"))
            or self.month_start_date(billing_month)
        )
        month_to_date_coverage = self.usage_coverage(month_to_date_usage_rows)
        month_to_date_end = (
            month_to_date_coverage[1]
            or self._parse_api_date(report_period.get("month_to_date_end"))
            or requested_end
        )
        month_to_date_estimate = self.build_estimate_fact(
            "MONTH_TO_DATE_ESTIMATE", month_to_date_start, month_to_date_end,
            month_to_date_coverage, month_to_date_cost_summary, calculated_at,
        )
        month_end_projection = self.build_month_end_projection(
            billing_month,
            bool(report_period.get("target_month_closed", False)),
            month_to_date_estimate,
            calculated_at,
        )
        confirmed_total = self.first_present(
            invoice_summary.get("total_amount"),
            sum(row["amount"] for row in service_summary),
            default=0.0,
        )
        cost_facts = [invoice_summary, period_estimate, month_to_date_estimate]
        if month_end_projection.get("status") != "NOT_APPLICABLE":
            cost_facts.append(month_end_projection)

        return {
            "summary": {
                "billing_month": billing_month,
                "confirmed_billing_month": confirmed_month,
                "days_in_month": days_in_month,
                "confirmed_total_amount": round(self.to_float(confirmed_total), 2),
                "confirmed_use_total_amount": round(confirmed_use_total, 2),
                "comparison_base_total_amount": round(confirmed_use_total, 2),
                "comparison_basis": "PRE_DISCOUNT_USE_AMOUNT",
                "expected_total_amount": round(expected_total, 2),
                "expected_total_amount_all": round(expected_total_all, 2),
                "month_to_date_expected_amount": month_to_date_estimate["total_amount"],
                "month_end_projection_amount": month_end_projection.get("total_amount"),
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
                "collection_warning_count": len(collection_warnings),
                "comparison_input_error_count": len(comparison_input_errors),
            },
            "service_summary": service_summary,
            "target_service_summary": target_service_summary,
            "discount_summary": discount_summary,
            "usage_summary": usage_summary,
            "network_usage_summary": network_usage_summary,
            "expected_cost_summary": expected_cost_summary,
            "month_to_date_cost_summary": month_to_date_cost_summary,
            "expected_by_service": expected_by_service,
            "comparison_summary": comparison_summary,
            "discount_rows": discount_rows,
            "demand_cost_rows": demand_rows,
            "confirmed_demand_cost_rows": confirmed_demand_rows,
            "demand_discount_rows": demand_discount_rows,
            "daily_usage_rows": daily_usage_rows,
            "month_to_date_usage_rows": month_to_date_usage_rows,
            "price_rows": price_rows,
            "collection_errors": collection_errors,
            "collection_warnings": collection_warnings,
            "invoice_summary": invoice_summary,
            "period_estimate": period_estimate,
            "month_to_date_estimate": month_to_date_estimate,
            "month_end_projection": month_end_projection,
            "cost_facts": cost_facts,
        }

    @staticmethod
    def _dict_list(value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @staticmethod
    def _verified_cost_rows(
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return [row for row in rows if row.get("calculation_status") == "OK"]

    @staticmethod
    def month_start_date(billing_month: str) -> date:
        return datetime.strptime(str(billing_month), "%Y%m").date().replace(day=1)

    @classmethod
    def month_bounds(cls, billing_month: str) -> Tuple[date, date]:
        start = cls.month_start_date(billing_month)
        end = start.replace(
            day=calendar.monthrange(start.year, start.month)[1]
        )
        return start, end

    @classmethod
    def report_period_dates(
        cls, period: Dict[str, Any], billing_month: str
    ) -> Tuple[date, date]:
        if not period.get("start_dt") or not period.get("end_dt"):
            return cls.month_bounds(billing_month)
        start = datetime.fromisoformat(str(period["start_dt"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(period["end_dt"]).replace("Z", "+00:00"))
        if period.get("end_exclusive"):
            end -= timedelta(microseconds=1)
        return start.date(), end.date()

    @classmethod
    def usage_coverage(
        cls, rows: List[Dict[str, Any]]
    ) -> Tuple[Optional[date], Optional[date]]:
        starts: List[date] = []
        ends: List[date] = []
        for row in rows:
            use_date = cls.as_dict(row.get("useDate"))
            start = cls._parse_api_date(use_date.get("useStartDate"))
            end = cls._parse_api_date(use_date.get("useEndDate"))
            if start:
                starts.append(start)
            if end:
                ends.append(end)
        return (min(starts) if starts else None, max(ends) if ends else None)

    @staticmethod
    def _parse_api_date(value: Any) -> Optional[date]:
        if value in (None, ""):
            return None
        normalized = str(value).strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).date()
        except ValueError:
            try:
                return datetime.strptime(normalized[:8], "%Y%m%d").date()
            except ValueError:
                return None

    def summarize_confirmed_invoice(
        self,
        rows: List[Dict[str, Any]],
        billing_month: str,
        calculated_at: Optional[str],
    ) -> Dict[str, Any]:
        period_start, period_end = self.month_bounds(billing_month)
        if not rows:
            return {
                "cost_type": "CONFIRMED",
                "status": "UNAVAILABLE",
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "coverage_start": None,
                "coverage_end": None,
                "calculated_at": calculated_at,
                "subtotal_amount": None,
                "discount_amount": None,
                "vat_amount": None,
                "total_amount": None,
                "currency": "KRW",
                "amount_basis": "CURRENT_MONTH_INVOICE_TOTAL",
                "includes_discount": True,
                "includes_vat": True,
                "confidence": "UNAVAILABLE",
                "excluded_item_count": 0,
                "source_api": "getDemandCostList",
                "calculation_version": "1.1",
                "details": {},
            }

        subtotal = sum(self.to_float(row.get("thisMonthDemandAmount")) for row in rows)
        vat = sum(self.to_float(row.get("thisMonthVatAmount")) for row in rows)
        total_demand = sum(
            self.to_float(row.get("totalDemandAmount")) for row in rows
        )
        current_including_vat = sum(
            self.to_float(row.get("thisMonthAmountIncludingVat")) for row in rows
        )
        has_current_invoice_total = any(
            row.get("thisMonthAmountIncludingVat") not in (None, "")
            for row in rows
        )
        has_current_components = any(
            row.get("thisMonthDemandAmount") not in (None, "")
            or row.get("thisMonthVatAmount") not in (None, "")
            for row in rows
        )
        total = (
            current_including_vat
            if has_current_invoice_total
            else subtotal + vat
            if has_current_components
            else total_demand
        )
        use_amount = sum(self.to_float(row.get("useAmount")) for row in rows)
        discount_keys = (
            "promiseDiscountAmount", "promotionDiscountAmount",
            "etcDiscountAmount", "customerDiscountAmount",
            "productDiscountAmount", "creditDiscountAmount",
            "rounddownDiscountAmount", "currencyDiscountAmount",
            "coinUseAmount", "memberPriceDiscountAmount",
            "memberPromiseDiscountAddAmount",
        )
        discount = sum(
            self.to_float(row.get(key)) for row in rows for key in discount_keys
        )
        write_dates = sorted(
            str(row.get("writeDate")) for row in rows if row.get("writeDate")
        )
        currencies = [
            str(self.as_dict(row.get("payCurrency")).get("code"))
            for row in rows
            if self.as_dict(row.get("payCurrency")).get("code")
        ]
        return {
            "cost_type": "CONFIRMED",
            "status": "AVAILABLE",
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "coverage_start": period_start.isoformat(),
            "coverage_end": period_end.isoformat(),
            "calculated_at": calculated_at,
            "subtotal_amount": round(subtotal, 2),
            "discount_amount": round(discount, 2),
            "vat_amount": round(vat, 2),
            "total_amount": round(total, 2),
            "currency": currencies[0] if currencies else "KRW",
            "amount_basis": "CURRENT_MONTH_INVOICE_TOTAL",
            "includes_discount": True,
            "includes_vat": True,
            "confidence": "CONFIRMED",
            "excluded_item_count": 0,
            "source_api": "getDemandCostList",
            "calculation_version": "1.1",
            "details": {
                "use_amount": round(use_amount, 2),
                "current_month_amount_including_vat": round(current_including_vat, 2),
                "total_demand_amount": round(total_demand, 2),
                "invoice_count": len(rows),
                "write_date": write_dates[-1] if write_dates else None,
                "is_paid_up": all(bool(row.get("isPaidUp")) for row in rows),
            },
        }

    def build_estimate_fact(
        self,
        cost_type: str,
        period_start: date,
        period_end: date,
        coverage: Tuple[Optional[date], Optional[date]],
        rows: List[Dict[str, Any]],
        calculated_at: Optional[str],
    ) -> Dict[str, Any]:
        verified = self._verified_cost_rows(rows)
        total = sum(self.to_float(row.get("expected_amount")) for row in verified)
        total_all = sum(self.to_float(row.get("expected_amount")) for row in rows)
        excluded = sum(row.get("calculation_status") != "OK" for row in rows)
        has_data = bool(rows)
        confidence = (
            "UNAVAILABLE" if not has_data
            else "PARTIAL" if excluded
            else "VERIFIED_ESTIMATE"
        )
        return {
            "cost_type": cost_type,
            "status": "AVAILABLE" if has_data else "UNAVAILABLE",
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "coverage_start": coverage[0].isoformat() if coverage[0] else None,
            "coverage_end": coverage[1].isoformat() if coverage[1] else None,
            "calculated_at": calculated_at,
            "subtotal_amount": round(total, 2),
            "discount_amount": None,
            "vat_amount": None,
            "total_amount": round(total, 2),
            "currency": "KRW",
            "amount_basis": "PRE_DISCOUNT_LIST_PRICE",
            "includes_discount": False,
            "includes_vat": False,
            "confidence": confidence,
            "excluded_item_count": int(excluded),
            "source_api": "getContractUsageListByDaily,getPriceList",
            "calculation_version": "1.1",
            "details": {
                "all_calculated_amount": round(total_all, 2),
                "row_count": len(rows),
            },
        }

    def build_month_end_projection(
        self,
        billing_month: str,
        target_month_closed: bool,
        month_to_date_estimate: Dict[str, Any],
        calculated_at: Optional[str],
    ) -> Dict[str, Any]:
        period_start, period_end = self.month_bounds(billing_month)
        base = {
            "cost_type": "MONTH_END_PROJECTION",
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "coverage_start": month_to_date_estimate.get("coverage_start"),
            "coverage_end": month_to_date_estimate.get("coverage_end"),
            "calculated_at": calculated_at,
            "discount_amount": None,
            "vat_amount": None,
            "currency": "KRW",
            "amount_basis": "DAILY_RUN_RATE_PROJECTION",
            "includes_discount": False,
            "includes_vat": False,
            "excluded_item_count": month_to_date_estimate.get("excluded_item_count", 0),
            "source_api": "getContractUsageListByDaily,getPriceList",
            "calculation_version": "1.1",
        }
        if target_month_closed:
            return {**base, "status": "NOT_APPLICABLE", "subtotal_amount": None,
                    "total_amount": None, "confidence": "UNAVAILABLE", "details": {}}
        coverage_start = self._parse_api_date(
            month_to_date_estimate.get("coverage_start")
        )
        coverage_end = self._parse_api_date(
            month_to_date_estimate.get("coverage_end")
        )
        if (
            not coverage_start
            or not coverage_end
            or month_to_date_estimate.get("status") != "AVAILABLE"
        ):
            return {**base, "status": "UNAVAILABLE", "subtotal_amount": None,
                    "total_amount": None, "confidence": "UNAVAILABLE", "details": {}}
        observed_days = (coverage_end - coverage_start).days + 1
        if observed_days <= 0:
            return {**base, "status": "UNAVAILABLE", "subtotal_amount": None,
                    "total_amount": None, "confidence": "UNAVAILABLE", "details": {}}
        projected = (
            self.to_float(month_to_date_estimate.get("total_amount"))
            / observed_days
            * period_end.day
        )
        confidence = (
            "PARTIAL" if month_to_date_estimate.get("confidence") == "PARTIAL"
            else "VERIFIED_ESTIMATE"
        )
        return {
            **base,
            "status": "AVAILABLE",
            "subtotal_amount": round(projected, 2),
            "total_amount": round(projected, 2),
            "confidence": confidence,
            "details": {"observed_days": observed_days, "month_days": period_end.day},
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
