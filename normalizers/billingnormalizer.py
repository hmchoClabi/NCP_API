import calendar
import math
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class _BillingInputs:
    raw_meta: Dict[str, Any]
    collection_errors: List[Dict[str, Any]]
    collection_warnings: List[Dict[str, Any]]
    comparison_input_errors: List[Dict[str, Any]]
    demand_rows: List[Dict[str, Any]]
    confirmed_demand_rows: List[Dict[str, Any]]
    confirmed_product_rows: List[Dict[str, Any]]
    contract_demand_rows: List[Dict[str, Any]]
    demand_discount_rows: List[Dict[str, Any]]
    daily_usage_rows: List[Dict[str, Any]]
    month_to_date_usage_rows: List[Dict[str, Any]]
    price_rows: List[Dict[str, Any]]
    discount_rows: List[Dict[str, Any]]


@dataclass(frozen=True)
class _BillingSummaries:
    service_summary: List[Dict[str, Any]]
    target_service_summary: List[Dict[str, Any]]
    contract_cost_summary: List[Dict[str, Any]]
    closed_cost_reference: List[Dict[str, Any]]
    closed_cost_source: str
    discount_summary: List[Dict[str, Any]]
    usage_summary: List[Dict[str, Any]]
    network_usage_summary: List[Dict[str, Any]]
    expected_cost_summary: List[Dict[str, Any]]
    month_to_date_cost_summary: List[Dict[str, Any]]
    expected_by_service: List[Dict[str, Any]]
    month_to_date_by_service: List[Dict[str, Any]]
    confirmed_use_total: float
    expected_total: float
    expected_total_all: float
    unverified_expected_amount: float


@dataclass(frozen=True)
class _BillingComparison:
    comparison_status: str
    calculation_status_counts: Dict[str, int]
    comparison_summary: List[Dict[str, Any]]
    diff_amount: Optional[float]
    diff_rate: Optional[float]


@dataclass(frozen=True)
class _BillingEstimates:
    confirmed_month: str
    invoice_summary: Dict[str, Any]
    period_estimate: Dict[str, Any]
    month_to_date_estimate: Dict[str, Any]
    projected_cost_summary: List[Dict[str, Any]]
    month_end_projection: Dict[str, Any]
    confirmed_total: Any
    cost_facts: List[Dict[str, Any]]


class BillingNormalizer:
    INCLUDED_CALCULATION_STATUSES = frozenset({"OK", "INFERRED"})

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
        include_account_breakdown: bool = True,
    ) -> Dict[str, Any]:
        billing_month = billing_month or current_month
        report_period = report_period or {}
        days_in_month = self.get_days_in_month(billing_month, use_end_date)

        inputs = self._extract_normalization_inputs(raw_data)
        summaries = self._summarize_confirmed_and_usage(
            inputs,
            days_in_month,
        )
        comparison = self._compare_confirmed_and_estimated(
            summaries,
            comparison_enabled=comparison_enabled,
            comparison_input_errors=inputs.comparison_input_errors,
        )
        estimates = self._build_usage_estimates(
            inputs,
            summaries,
            billing_month=billing_month,
            days_in_month=days_in_month,
            report_period=report_period,
            calculated_at=calculated_at,
        )
        organization, account_costs = self._summarize_organization_accounts(
            raw_data,
            inputs.raw_meta,
            billing_month=billing_month,
            use_end_date=use_end_date,
            comparison_enabled=comparison_enabled,
            report_period=report_period,
            calculated_at=calculated_at,
            include_account_breakdown=include_account_breakdown,
        )
        return self._assemble_normalized_payload(
            billing_month=billing_month,
            days_in_month=days_in_month,
            inputs=inputs,
            summaries=summaries,
            comparison=comparison,
            estimates=estimates,
            organization=organization,
            account_costs=account_costs,
        )

    def _extract_normalization_inputs(
        self,
        raw_data: Dict[str, Any],
    ) -> _BillingInputs:
        """수집 응답의 기존 envelope와 fallback 순서를 유지해 입력을 추출한다."""

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
        contract_demand_rows = self.extract_rows(
            raw_data.get("contract_demand_cost", []),
            "contractDemandCostList",
        )
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
        price_rows = self.merge_price_rows(
            self.extract_rows(
                raw_data.get("product_price_list", []), "priceList"
            ),
            self.extract_rows(raw_data.get("price_list", []), "priceList"),
        )
        discount_rows = self.extract_rows(
            raw_data.get("discount_list", []), "discountList"
        )
        return _BillingInputs(
            raw_meta=raw_meta,
            collection_errors=collection_errors,
            collection_warnings=collection_warnings,
            comparison_input_errors=comparison_input_errors,
            demand_rows=demand_rows,
            confirmed_demand_rows=confirmed_demand_rows,
            confirmed_product_rows=confirmed_product_rows,
            contract_demand_rows=contract_demand_rows,
            demand_discount_rows=demand_discount_rows,
            daily_usage_rows=daily_usage_rows,
            month_to_date_usage_rows=month_to_date_usage_rows,
            price_rows=price_rows,
            discount_rows=discount_rows,
        )

    def _summarize_confirmed_and_usage(
        self,
        inputs: _BillingInputs,
        days_in_month: int,
    ) -> _BillingSummaries:
        """확정 금액과 사용량 기반 금액을 기존 계산 기준으로 각각 요약한다."""

        # 확정 비용은 할인 전 useAmount를 비교 기준으로 사용한다.
        service_summary = self.summarize_confirmed_by_service(
            inputs.confirmed_product_rows
        )
        target_service_summary = self.summarize_confirmed_by_service(
            inputs.demand_rows
        )
        contract_cost_summary = self.summarize_contract_demand_by_service(
            inputs.contract_demand_rows
        )
        closed_cost_reference = target_service_summary or contract_cost_summary
        closed_cost_source = (
            "getProductDemandCostList"
            if target_service_summary
            else "getContractDemandCostList"
        )
        discount_summary = self.summarize_discount_by_service(
            inputs.demand_discount_rows
        )
        usage_summary = self.summarize_usage(inputs.daily_usage_rows)
        network_usage_summary = self.summarize_network_usage(
            inputs.daily_usage_rows
        )
        expected_cost_summary = self.summarize_expected_cost(
            usage_rows=inputs.daily_usage_rows,
            price_rows=inputs.price_rows,
            days_in_month=days_in_month,
        )
        month_to_date_cost_summary = self.summarize_expected_cost(
            usage_rows=inputs.month_to_date_usage_rows,
            price_rows=inputs.price_rows,
            days_in_month=days_in_month,
        )

        verified_expected_rows = self._included_cost_rows(expected_cost_summary)
        expected_by_service = self.summarize_expected_by_service(
            verified_expected_rows
        )
        month_to_date_by_service = self.summarize_expected_by_service(
            self._included_cost_rows(month_to_date_cost_summary)
        )
        confirmed_use_total = sum(
            row["use_amount"] for row in target_service_summary
        )
        expected_total = sum(
            row["expected_amount"] for row in verified_expected_rows
        )
        expected_total_all = sum(
            row["expected_amount"] for row in expected_cost_summary
        )
        return _BillingSummaries(
            service_summary=service_summary,
            target_service_summary=target_service_summary,
            contract_cost_summary=contract_cost_summary,
            closed_cost_reference=closed_cost_reference,
            closed_cost_source=closed_cost_source,
            discount_summary=discount_summary,
            usage_summary=usage_summary,
            network_usage_summary=network_usage_summary,
            expected_cost_summary=expected_cost_summary,
            month_to_date_cost_summary=month_to_date_cost_summary,
            expected_by_service=expected_by_service,
            month_to_date_by_service=month_to_date_by_service,
            confirmed_use_total=confirmed_use_total,
            expected_total=expected_total,
            expected_total_all=expected_total_all,
            unverified_expected_amount=expected_total_all - expected_total,
        )

    def _compare_confirmed_and_estimated(
        self,
        summaries: _BillingSummaries,
        *,
        comparison_enabled: bool,
        comparison_input_errors: List[Dict[str, Any]],
    ) -> _BillingComparison:
        """검증된 예상 금액만 확정 금액과 비교해 신뢰도 상태를 보존한다."""

        calculation_status_counts = dict(Counter(
            row.get("calculation_status") or "UNKNOWN"
            for row in summaries.expected_cost_summary
        ))
        has_unverified_expected = any(
            status != "OK" for status in calculation_status_counts
        )
        if (
            comparison_enabled
            and not summaries.expected_cost_summary
            and summaries.confirmed_use_total != 0
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

        comparison_summary = (
            self.compare_confirmed_and_expected(
                confirmed_summary=summaries.target_service_summary,
                expected_summary=summaries.expected_by_service,
            )
            if comparison_status == "OK" else []
        )
        diff_amount: Optional[float] = None
        diff_rate: Optional[float] = None
        if comparison_status == "OK":
            diff_amount = round(
                summaries.expected_total - summaries.confirmed_use_total,
                2,
            )
            diff_rate = self.safe_rate(
                diff_amount,
                summaries.confirmed_use_total,
            )
        return _BillingComparison(
            comparison_status=comparison_status,
            calculation_status_counts=calculation_status_counts,
            comparison_summary=comparison_summary,
            diff_amount=diff_amount,
            diff_rate=diff_rate,
        )

    def _build_usage_estimates(
        self,
        inputs: _BillingInputs,
        summaries: _BillingSummaries,
        *,
        billing_month: str,
        days_in_month: int,
        report_period: Dict[str, Any],
        calculated_at: Optional[str],
    ) -> _BillingEstimates:
        """기간·월 누적·월말 추정치를 기존 fallback 우선순위로 구성한다."""

        confirmed_month = str(
            inputs.raw_meta.get("confirmed_demand_month")
            or report_period.get("confirmed_demand_month")
            or billing_month
        )
        invoice_summary = self.summarize_confirmed_invoice(
            inputs.confirmed_demand_rows,
            confirmed_month,
            calculated_at,
        )
        requested_start, requested_end = self.report_period_dates(
            report_period, billing_month
        )
        local_period_estimate = self.build_estimate_fact(
            "PERIOD_ESTIMATE", requested_start, requested_end,
            self.usage_coverage(inputs.daily_usage_rows),
            summaries.expected_cost_summary,
            calculated_at,
        )
        month_to_date_start = (
            self._parse_api_date(report_period.get("month_to_date_start"))
            or self.month_start_date(billing_month)
        )
        month_to_date_coverage = self.usage_coverage(
            inputs.month_to_date_usage_rows
        )
        requested_month_to_date_end = self._parse_api_date(
            report_period.get("month_to_date_end")
        )
        month_to_date_end = (
            month_to_date_coverage[1]
            or requested_month_to_date_end
            or requested_end
        )
        local_month_to_date_estimate = self.build_estimate_fact(
            "MONTH_TO_DATE_ESTIMATE", month_to_date_start, month_to_date_end,
            month_to_date_coverage,
            summaries.month_to_date_cost_summary,
            calculated_at,
        )
        target_month_start, target_month_end = self.month_bounds(billing_month)
        target_month_closed = bool(
            report_period.get("target_month_closed", False)
        )
        calculated_date = self._parse_api_date(calculated_at)
        ncp_write_date = self.latest_write_date(inputs.demand_rows)
        all_ncp_rows_fresh = self.all_rows_written_on_or_after(
            inputs.demand_rows,
            month_to_date_end,
        )
        cutoff_age_days = (
            (calculated_date - month_to_date_end).days
            if calculated_date
            else None
        )
        ncp_current_eligible = bool(
            summaries.target_service_summary
            and not target_month_closed
            and cutoff_age_days is not None
            and 0 <= cutoff_age_days <= 1
            and ncp_write_date
            and all_ncp_rows_fresh
        )
        full_closed_month = bool(
            target_month_closed
            and requested_start == target_month_start
            and requested_end == target_month_end
        )

        # 확정 월, 최신 NCP 금액, 로컬 계산 순서가 신뢰도 표시를 결정한다.
        if full_closed_month and summaries.closed_cost_reference:
            period_estimate = self.build_ncp_usage_fact(
                "PERIOD_ESTIMATE",
                requested_start,
                requested_end,
                requested_start,
                requested_end,
                summaries.closed_cost_reference,
                calculated_at,
                closed_month=True,
                source_api=summaries.closed_cost_source,
            )
        elif (
            not target_month_closed
            and requested_start == month_to_date_start
            and requested_end >= month_to_date_end
        ):
            period_estimate = self.not_applicable_fact(local_period_estimate)
        else:
            period_estimate = local_period_estimate

        if full_closed_month or (
            target_month_closed
            and requested_start == month_to_date_start
            and requested_end == month_to_date_end
        ):
            month_to_date_estimate = self.not_applicable_fact(
                local_month_to_date_estimate
            )
        elif (
            ncp_current_eligible
            and local_month_to_date_estimate.get("excluded_item_count", 0) > 0
        ):
            month_to_date_estimate = self.apply_ncp_current_fallback(
                local_month_to_date_estimate,
                summaries.target_service_summary,
                ncp_write_date,
            )
        else:
            month_to_date_estimate = local_month_to_date_estimate

        projected_cost_summary: List[Dict[str, Any]] = []
        if not target_month_closed and inputs.month_to_date_usage_rows:
            projected_usage_rows = self.project_usage_to_month_end(
                inputs.month_to_date_usage_rows,
                target_month_start,
                month_to_date_end,
                target_month_end,
                price_rows=inputs.price_rows,
            )
            projected_cost_summary = self.summarize_expected_cost(
                usage_rows=projected_usage_rows,
                price_rows=inputs.price_rows,
                days_in_month=days_in_month,
            )
        month_end_projection = self.build_month_end_projection(
            billing_month,
            target_month_closed,
            month_to_date_estimate,
            calculated_at,
            current_cost_rows=summaries.month_to_date_cost_summary,
            projected_cost_rows=projected_cost_summary,
            ncp_service_summary=(
                summaries.target_service_summary
                if ncp_current_eligible
                else summaries.closed_cost_reference
                if target_month_closed and not full_closed_month
                else []
            ),
            ncp_reference_source=(
                "getProductDemandCostList"
                if ncp_current_eligible
                else summaries.closed_cost_source
            ),
        )
        confirmed_total = self.first_present(
            invoice_summary.get("total_amount"),
            sum(row["amount"] for row in summaries.service_summary),
            default=0.0,
        )
        cost_facts = [invoice_summary]
        if period_estimate.get("status") != "NOT_APPLICABLE":
            cost_facts.append(period_estimate)
        if month_to_date_estimate.get("status") != "NOT_APPLICABLE":
            cost_facts.append(month_to_date_estimate)
        if month_end_projection.get("status") != "NOT_APPLICABLE":
            cost_facts.append(month_end_projection)
        return _BillingEstimates(
            confirmed_month=confirmed_month,
            invoice_summary=invoice_summary,
            period_estimate=period_estimate,
            month_to_date_estimate=month_to_date_estimate,
            projected_cost_summary=projected_cost_summary,
            month_end_projection=month_end_projection,
            confirmed_total=confirmed_total,
            cost_facts=cost_facts,
        )

    def _summarize_organization_accounts(
        self,
        raw_data: Dict[str, Any],
        raw_meta: Dict[str, Any],
        *,
        billing_month: str,
        use_end_date: Optional[str],
        comparison_enabled: bool,
        report_period: Dict[str, Any],
        calculated_at: Optional[str],
        include_account_breakdown: bool,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Organization 범위일 때만 기존 계정별 정규화를 재사용한다."""

        organization = self.as_dict(raw_meta.get("organization"))
        account_costs = (
            self.build_account_costs(
                raw_data, organization, billing_month, use_end_date,
                comparison_enabled, report_period, calculated_at,
            )
            if include_account_breakdown
            and organization.get("scope") == "ORGANIZATION"
            else []
        )
        return organization, account_costs

    def _assemble_normalized_payload(
        self,
        *,
        billing_month: str,
        days_in_month: int,
        inputs: _BillingInputs,
        summaries: _BillingSummaries,
        comparison: _BillingComparison,
        estimates: _BillingEstimates,
        organization: Dict[str, Any],
        account_costs: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """금액 기준과 키 순서를 유지해 기존 공개 payload를 조립한다."""

        return {
            "summary": {
                "billing_month": billing_month,
                "confirmed_billing_month": estimates.confirmed_month,
                "days_in_month": days_in_month,
                "confirmed_total_amount": round(
                    self.to_float(estimates.confirmed_total), 2
                ),
                "confirmed_use_total_amount": round(
                    summaries.confirmed_use_total, 2
                ),
                "comparison_base_total_amount": round(
                    summaries.confirmed_use_total, 2
                ),
                "comparison_basis": "PRE_DISCOUNT_USE_AMOUNT",
                "expected_total_amount": round(summaries.expected_total, 2),
                "expected_total_amount_all": round(
                    summaries.expected_total_all, 2
                ),
                "month_to_date_expected_amount": (
                    estimates.month_to_date_estimate.get("total_amount")
                ),
                "month_end_projection_amount": (
                    estimates.month_end_projection.get("total_amount")
                ),
                "unverified_expected_amount": round(
                    summaries.unverified_expected_amount, 2
                ),
                "diff_amount": comparison.diff_amount,
                "diff_rate": comparison.diff_rate,
                "comparison_status": comparison.comparison_status,
                "calculation_status_counts": (
                    comparison.calculation_status_counts
                ),
                "service_count": len(summaries.service_summary),
                "usage_summary_count": len(summaries.usage_summary),
                "network_usage_count": len(summaries.network_usage_summary),
                "expected_cost_count": len(summaries.expected_cost_summary),
                "discount_count": len(inputs.discount_rows),
                "collection_error_count": len(inputs.collection_errors),
                "collection_warning_count": len(inputs.collection_warnings),
                "comparison_input_error_count": len(
                    inputs.comparison_input_errors
                ),
            },
            "service_summary": summaries.service_summary,
            "target_service_summary": summaries.target_service_summary,
            "discount_summary": summaries.discount_summary,
            "usage_summary": summaries.usage_summary,
            "network_usage_summary": summaries.network_usage_summary,
            "expected_cost_summary": summaries.expected_cost_summary,
            "month_to_date_cost_summary": summaries.month_to_date_cost_summary,
            "projected_cost_summary": estimates.projected_cost_summary,
            "expected_by_service": summaries.expected_by_service,
            "month_to_date_by_service": summaries.month_to_date_by_service,
            "comparison_summary": comparison.comparison_summary,
            "discount_rows": inputs.discount_rows,
            "demand_cost_rows": inputs.demand_rows,
            "contract_demand_cost_rows": inputs.contract_demand_rows,
            "contract_cost_summary": summaries.contract_cost_summary,
            "confirmed_demand_cost_rows": inputs.confirmed_demand_rows,
            "demand_discount_rows": inputs.demand_discount_rows,
            "daily_usage_rows": inputs.daily_usage_rows,
            "month_to_date_usage_rows": inputs.month_to_date_usage_rows,
            "price_rows": inputs.price_rows,
            "collection_errors": inputs.collection_errors,
            "collection_warnings": inputs.collection_warnings,
            "invoice_summary": estimates.invoice_summary,
            "period_estimate": estimates.period_estimate,
            "month_to_date_estimate": estimates.month_to_date_estimate,
            "month_end_projection": estimates.month_end_projection,
            "cost_facts": estimates.cost_facts,
            "organization": organization,
            "account_costs": account_costs,
        }

    def build_account_costs(
        self,
        raw_data: Dict[str, Any],
        organization: Dict[str, Any],
        billing_month: str,
        use_end_date: Optional[str],
        comparison_enabled: bool,
        report_period: Dict[str, Any],
        calculated_at: Optional[str],
    ) -> List[Dict[str, Any]]:
        members = [
            item for item in organization.get("members", [])
            if isinstance(item, dict) and item.get("member_no")
        ]
        result: List[Dict[str, Any]] = []
        for member in members:
            member_no = str(member["member_no"])
            member_raw = self._raw_for_member(raw_data, member_no)
            normalized = self.normalize(
                member_raw,
                billing_month=billing_month,
                use_end_date=use_end_date,
                comparison_enabled=comparison_enabled,
                report_period=report_period,
                calculated_at=calculated_at,
                include_account_breakdown=False,
            )
            current_services = normalized["target_service_summary"]
            current_amount = sum(
                self.to_float(row.get("amount")) for row in current_services
            )
            current_use_amount = sum(
                self.to_float(row.get("use_amount")) for row in current_services
            )
            current_start, current_end = self.month_bounds(billing_month)
            provisional_coverage_end = self._parse_api_date(
                report_period.get("month_to_date_end")
            )
            current_fact = {
                "cost_type": "CURRENT_PROVISIONAL",
                "status": "AVAILABLE" if current_services else "UNAVAILABLE",
                "period_start": current_start.isoformat(),
                "period_end": current_end.isoformat(),
                "coverage_start": current_start.isoformat() if current_services else None,
                "coverage_end": (
                    provisional_coverage_end.isoformat()
                    if provisional_coverage_end else None
                ),
                "calculated_at": calculated_at,
                "subtotal_amount": round(current_amount, 2) if current_services else None,
                "vat_amount": None,
                "total_amount": round(current_amount, 2) if current_services else None,
                "currency": "KRW",
                "amount_basis": "NCP_CURRENT_PRODUCT_DEMAND",
                "includes_discount": True,
                "includes_vat": False,
                "confidence": "PROVISIONAL" if current_services else "UNAVAILABLE",
                "source_api": "getProductDemandCostList",
                "calculation_version": "1.2",
                "details": {"use_amount": round(current_use_amount, 2)},
            }
            account_facts = list(normalized["cost_facts"])
            if not bool(report_period.get("target_month_closed", False)):
                account_facts.append(current_fact)
            else:
                current_services = []
            result.append({
                **member,
                "summary": normalized["summary"],
                "cost_facts": account_facts,
                "service_summary": normalized["service_summary"],
                "current_service_summary": current_services,
                "expected_by_service": normalized["expected_by_service"],
            })
        return result

    def _raw_for_member(
        self, raw_data: Dict[str, Any], member_no: str
    ) -> Dict[str, Any]:
        list_keys = {
            "demand_cost": "demandCostList",
            "product_demand_cost": "productDemandCostList",
            "confirmed_demand_cost": "demandCostList",
            "confirmed_product_demand_cost": "productDemandCostList",
            "contract_demand_cost": "contractDemandCostList",
            "product_demand_cost_by_discount": "productDemandCostByDiscountList",
            "discount_list": "discountList",
            "daily_usage": "contractUsageListByDaily",
            "month_to_date_usage": "contractUsageListByDaily",
        }
        filtered: Dict[str, Any] = {
            "price_list": raw_data.get("price_list", []),
            "product_price_list": raw_data.get("product_price_list", []),
            "_meta": {
                key: value for key, value in self.as_dict(raw_data.get("_meta")).items()
                if key != "organization"
            },
        }
        for source, list_key in list_keys.items():
            rows = self.extract_rows(raw_data.get(source, []), list_key)
            filtered[source] = [{list_key: [
                row for row in rows if self._row_member_no(row) == member_no
            ]}]
        return filtered

    @classmethod
    def _row_member_no(cls, row: Dict[str, Any]) -> str:
        return str(cls.first_present(
            row.get("memberNo"),
            cls.as_dict(row.get("account")).get("memberNo"),
            cls.as_dict(row.get("contract")).get("memberNo"),
            default="",
        ))

    @staticmethod
    def _dict_list(value: Any) -> List[Dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    @classmethod
    def _included_cost_rows(
        cls,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        return [
            row for row in rows
            if row.get("calculation_status") in cls.INCLUDED_CALCULATION_STATUSES
        ]

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
                "calculation_version": "1.2",
                "details": {},
            }

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
        stated_subtotal = sum(
            self.to_float(row.get("thisMonthDemandAmount")) for row in rows
        )
        subtotal = (
            current_including_vat - vat
            if has_current_invoice_total
            else stated_subtotal
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
            "calculation_version": "1.2",
            "details": {
                "use_amount": round(use_amount, 2),
                "current_month_amount_including_vat": round(current_including_vat, 2),
                "total_demand_amount": round(total_demand, 2),
                "invoice_count": len(rows),
                "write_date": write_dates[-1] if write_dates else None,
                "is_paid_up": all(bool(row.get("isPaidUp")) for row in rows),
            },
        }

    def build_ncp_usage_fact(
        self,
        cost_type: str,
        period_start: date,
        period_end: date,
        coverage_start: date,
        coverage_end: date,
        service_rows: List[Dict[str, Any]],
        calculated_at: Optional[str],
        closed_month: bool,
        source_api: str = "getProductDemandCostList",
    ) -> Dict[str, Any]:
        total = sum(self.to_float(row.get("use_amount")) for row in service_rows)
        return {
            "cost_type": cost_type,
            "status": "AVAILABLE" if service_rows else "UNAVAILABLE",
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "coverage_start": coverage_start.isoformat() if service_rows else None,
            "coverage_end": coverage_end.isoformat() if service_rows else None,
            "calculated_at": calculated_at,
            "subtotal_amount": round(total, 2) if service_rows else None,
            "discount_amount": None,
            "vat_amount": None,
            "total_amount": round(total, 2) if service_rows else None,
            "currency": "KRW",
            "amount_basis": (
                "NCP_CONTRACT_DEMAND_USE_AMOUNT"
                if source_api == "getContractDemandCostList"
                else "NCP_PRODUCT_DEMAND_USE_AMOUNT"
            ),
            "includes_discount": False,
            "includes_vat": False,
            "confidence": (
                "VERIFIED_ESTIMATE" if closed_month else "PARTIAL"
            ) if service_rows else "UNAVAILABLE",
            "excluded_item_count": 0,
            "source_api": source_api,
            "calculation_version": "2.0",
            "details": {
                "service_count": len(service_rows),
                "scope": "CLOSED_MONTH" if closed_month else "MONTH_TO_DATE",
            },
        }

    @classmethod
    def latest_write_date(
        cls,
        rows: List[Dict[str, Any]],
    ) -> Optional[date]:
        values = [
            parsed
            for parsed in (
                cls._parse_api_date(row.get("writeDate"))
                for row in rows
            )
            if parsed is not None
        ]
        return max(values) if values else None

    @classmethod
    def all_rows_written_on_or_after(
        cls,
        rows: List[Dict[str, Any]],
        cutoff: date,
    ) -> bool:
        if not rows:
            return False
        values = [
            cls._parse_api_date(row.get("writeDate")) for row in rows
        ]
        return bool(
            all(value is not None for value in values)
            and min(value for value in values if value is not None) >= cutoff
        )

    def apply_ncp_current_fallback(
        self,
        local_fact: Dict[str, Any],
        service_rows: List[Dict[str, Any]],
        ncp_write_date: date,
    ) -> Dict[str, Any]:
        ncp_total = sum(
            self.to_float(row.get("use_amount")) for row in service_rows
        )
        details = self.as_dict(local_fact.get("details"))
        return {
            **local_fact,
            "subtotal_amount": round(ncp_total, 2),
            "total_amount": round(ncp_total, 2),
            "amount_basis": "NCP_CURRENT_USE_AMOUNT_FALLBACK",
            "confidence": "PARTIAL",
            "source_api": (
                "getProductDemandCostList,"
                "getContractUsageListByDaily,getPriceList,getProductPriceList"
            ),
            "details": {
                **details,
                "local_calculated_amount": local_fact.get("total_amount"),
                "ncp_reference_write_date": ncp_write_date.isoformat(),
                "fallback_reason": "UNSUPPORTED_COMPLEX_PRICE_ROWS",
                "coverage_assumption": (
                    "All NCP current-month rows were written on or after the "
                    "report cutoff; "
                    "the API does not expose an explicit usage cutoff."
                ),
            },
        }

    @staticmethod
    def not_applicable_fact(fact: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **fact,
            "status": "NOT_APPLICABLE",
            "subtotal_amount": None,
            "total_amount": None,
            "confidence": "UNAVAILABLE",
        }

    def project_usage_to_month_end(
        self,
        rows: List[Dict[str, Any]],
        month_start: date,
        coverage_end: date,
        month_end: date,
        price_rows: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        projected = deepcopy(rows)
        if not rows or coverage_end >= month_end:
            return projected

        price_map = self.build_price_map(price_rows or [])
        groups: Dict[Tuple[str, ...], List[Dict[str, Any]]] = defaultdict(list)
        for row in rows:
            contract = self.as_dict(row.get("contract"))
            product = self.as_dict(row.get("contractProduct"))
            price_no = self.get_price_no(row)
            price_row = price_map.get(price_no, {})
            stateful = self.is_stateful_projection_price(price_row)
            key = (
                self._row_member_no(row),
                str(contract.get("contractNo") or ""),
                str(
                    product.get("contractProductSequence")
                    or product.get("instanceNo")
                    or ""
                ),
                price_no,
                "STATEFUL" if stateful else self.get_metering_type_code(row),
                self.get_usage_unit_code(row),
            )
            groups[key].append(row)

        for grouped_rows in groups.values():
            total_user_quantity = sum(
                self.get_usage_quantity(row) for row in grouped_rows
            )
            if total_user_quantity <= 0:
                continue
            price_row = price_map.get(self.get_price_no(grouped_rows[0]), {})
            stateful = self.is_stateful_projection_price(price_row)
            observed_dates = [
                self._parse_api_date(
                    self.as_dict(row.get("useDate")).get("useStartDate")
                )
                for row in grouped_rows
            ]
            observed_dates = [value for value in observed_dates if value]
            observed_start = min(observed_dates) if observed_dates else month_start
            source_row = max(
                grouped_rows,
                key=lambda row: (
                    self._parse_api_date(
                        self.as_dict(row.get("useDate")).get("useEndDate")
                    )
                    or date.min,
                    self._parse_api_date(
                        self.as_dict(row.get("useDate")).get("useStartDate")
                    )
                    or date.min,
                    -self.get_effective_price(row, price_row)[0],
                    self.get_product_count(row) or 0.0,
                ),
            ) if stateful else grouped_rows[0]
            product = self.as_dict(source_row.get("contractProduct"))
            service_start = self._parse_api_date(product.get("serviceStartDate"))
            if service_start:
                observed_start = max(observed_start, service_start)
            observed_start = max(observed_start, month_start)
            observed_days = (coverage_end - observed_start).days + 1
            if observed_days <= 0:
                continue

            future_end = month_end
            service_end = self._parse_api_date(product.get("serviceEndDate"))
            if service_end and service_end < future_end:
                future_end = service_end
            future_start = coverage_end + timedelta(days=1)
            if future_end < future_start:
                continue
            future_days = (future_end - future_start).days + 1
            factor = future_days / observed_days

            synthetic = deepcopy(source_row)
            usage = self.as_dict(synthetic.get("usage"))
            if stateful:
                source_date = self.as_dict(source_row.get("useDate"))
                source_start = self._parse_api_date(
                    source_date.get("useStartDate")
                )
                source_end = self._parse_api_date(source_date.get("useEndDate"))
                source_days = (
                    (source_end - source_start).days + 1
                    if source_start and source_end and source_end >= source_start
                    else 1
                )
                source_user_quantity = self.get_usage_quantity(source_row)
                source_unit_code = self.get_usage_unit_code(source_row)
                if source_unit_code == "HOUR":
                    future_user_quantity = future_days * 24
                elif source_unit_code in {"SEC_DAY", "DAY", "USAGE_DAY"}:
                    future_user_quantity = future_days
                else:
                    future_user_quantity = (
                        source_user_quantity / source_days * future_days
                    )
                usage["userUsageQuantity"] = future_user_quantity
                source_raw_quantity = self.to_float(
                    self.as_dict(source_row.get("usage")).get("usageQuantity")
                )
                if source_raw_quantity:
                    usage["usageQuantity"] = (
                        source_raw_quantity
                        / source_user_quantity
                        * future_user_quantity
                        if source_user_quantity > 0
                        else source_raw_quantity / source_days * future_days
                    )
                projection_method = "LATEST_STATE"
            else:
                usage["userUsageQuantity"] = total_user_quantity * factor
                raw_quantities = [
                    self.to_float(
                        self.as_dict(row.get("usage")).get("usageQuantity")
                    )
                    for row in grouped_rows
                ]
                if any(raw_quantities):
                    usage["usageQuantity"] = sum(raw_quantities) * factor
                projection_method = "HISTORICAL_DAILY_RUN_RATE"
            synthetic["usage"] = usage
            synthetic["useDate"] = {
                "useStartDate": future_start.isoformat(),
                "useEndDate": future_end.isoformat(),
            }
            synthetic["_projection"] = True
            synthetic["_projection_method"] = projection_method
            projected.append(synthetic)

        return projected

    def build_estimate_fact(
        self,
        cost_type: str,
        period_start: date,
        period_end: date,
        coverage: Tuple[Optional[date], Optional[date]],
        rows: List[Dict[str, Any]],
        calculated_at: Optional[str],
    ) -> Dict[str, Any]:
        included = self._included_cost_rows(rows)
        total = sum(self.to_float(row.get("expected_amount")) for row in included)
        total_all = sum(self.to_float(row.get("expected_amount")) for row in rows)
        excluded = sum(
            row.get("calculation_status") not in self.INCLUDED_CALCULATION_STATUSES
            for row in rows
        )
        inferred = sum(
            row.get("calculation_status") == "INFERRED" for row in rows
        )
        has_data = bool(rows)
        incomplete_coverage = bool(
            has_data
            and (
                coverage[0] is None
                or coverage[1] is None
                or coverage[0] > period_start
                or coverage[1] < period_end
            )
        )
        confidence = (
            "UNAVAILABLE" if not has_data
            else "PARTIAL" if excluded or inferred or incomplete_coverage
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
            "source_api": (
                "getContractUsageListByDaily,getPriceList,getProductPriceList"
            ),
            "calculation_version": "2.0",
            "details": {
                "all_calculated_amount": round(total_all, 2),
                "row_count": len(rows),
                "inferred_item_count": int(inferred),
                "incomplete_coverage": incomplete_coverage,
            },
        }

    def build_month_end_projection(
        self,
        billing_month: str,
        target_month_closed: bool,
        month_to_date_estimate: Dict[str, Any],
        calculated_at: Optional[str],
        current_cost_rows: Optional[List[Dict[str, Any]]] = None,
        projected_cost_rows: Optional[List[Dict[str, Any]]] = None,
        ncp_service_summary: Optional[List[Dict[str, Any]]] = None,
        ncp_reference_source: str = "getProductDemandCostList",
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
            "amount_basis": "PROJECTED_USAGE_RERATED",
            "includes_discount": False,
            "includes_vat": False,
            "excluded_item_count": month_to_date_estimate.get("excluded_item_count", 0),
            "source_api": (
                "getContractUsageListByDaily,getPriceList,getProductPriceList"
            ),
            "calculation_version": "2.0",
        }
        ncp_service_summary = ncp_service_summary or []
        if target_month_closed:
            if ncp_service_summary:
                total = sum(
                    self.to_float(row.get("use_amount"))
                    for row in ncp_service_summary
                )
                return {
                    **base,
                    "status": "AVAILABLE",
                    "coverage_start": period_start.isoformat(),
                    "coverage_end": period_end.isoformat(),
                    "subtotal_amount": round(total, 2),
                    "total_amount": round(total, 2),
                    "amount_basis": (
                        "NCP_CONTRACT_DEMAND_USE_AMOUNT"
                        if ncp_reference_source == "getContractDemandCostList"
                        else "NCP_PRODUCT_DEMAND_USE_AMOUNT"
                    ),
                    "confidence": "VERIFIED_ESTIMATE",
                    "source_api": ncp_reference_source,
                    "details": {
                        "service_count": len(ncp_service_summary),
                        "closed_month_actual": True,
                        "inferred_item_count": 0,
                    },
                }
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
        observation_start = (
            self._parse_api_date(month_to_date_estimate.get("period_start"))
            or coverage_start
        )
        observed_days = (coverage_end - observation_start).days + 1
        if observed_days <= 0:
            return {**base, "status": "UNAVAILABLE", "subtotal_amount": None,
                    "total_amount": None, "confidence": "UNAVAILABLE", "details": {}}
        current_cost_rows = current_cost_rows or []
        projected_cost_rows = projected_cost_rows or []
        included_projected = self._included_cost_rows(projected_cost_rows)
        excluded = sum(
            row.get("calculation_status") not in self.INCLUDED_CALCULATION_STATUSES
            for row in projected_cost_rows
        )
        inferred = sum(
            row.get("calculation_status") == "INFERRED"
            for row in projected_cost_rows
        )

        if projected_cost_rows:
            current_by_service = self._cost_rows_by_service(
                self._included_cost_rows(current_cost_rows)
            )
            projected_by_service = self._cost_rows_by_service(included_projected)
            if ncp_service_summary:
                projected, fallback_services = self.calibrate_month_projection(
                    ncp_service_summary,
                    current_by_service,
                    projected_by_service,
                    observed_days,
                    period_end.day,
                )
                amount_basis = (
                    "NCP_ACCRUED_LOWER_BOUND"
                    if not current_by_service
                    else "NCP_ACCRUED_PLUS_USAGE_FORECAST"
                )
                source_api = (
                    "getProductDemandCostList,"
                    "getContractUsageListByDaily,getPriceList,getProductPriceList"
                )
            else:
                projected = sum(
                    self.to_float(row.get("expected_amount"))
                    for row in included_projected
                )
                fallback_services = 0
                amount_basis = "PROJECTED_USAGE_RERATED"
                source_api = (
                    "getContractUsageListByDaily,getPriceList,"
                    "getProductPriceList"
                )
        else:
            projected = (
                self.to_float(month_to_date_estimate.get("total_amount"))
                / observed_days
                * period_end.day
            )
            fallback_services = 1
            amount_basis = "DAILY_RUN_RATE_PROJECTION"
            source_api = str(base["source_api"])

        confidence = (
            "PARTIAL"
            if (
                excluded
                or inferred
                or fallback_services
                or ncp_service_summary
                or month_to_date_estimate.get("confidence") == "PARTIAL"
            )
            else "VERIFIED_ESTIMATE"
        )
        return {
            **base,
            "amount_basis": amount_basis,
            "source_api": source_api,
            "excluded_item_count": int(excluded),
            "status": "AVAILABLE",
            "subtotal_amount": round(projected, 2),
            "total_amount": round(projected, 2),
            "confidence": confidence,
            "details": {
                "observed_days": observed_days,
                "month_days": period_end.day,
                "projected_item_count": len(projected_cost_rows),
                "inferred_item_count": int(inferred),
                "fallback_service_count": int(fallback_services),
            },
        }

    def _cost_rows_by_service(
        self,
        rows: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        result: Dict[str, float] = defaultdict(float)
        for row in rows:
            key = self.normalize_service_key(row.get("service_name"))
            result[key] += self.to_float(row.get("expected_amount"))
        return dict(result)

    def calibrate_month_projection(
        self,
        ncp_service_summary: List[Dict[str, Any]],
        current_by_service: Dict[str, float],
        projected_by_service: Dict[str, float],
        observed_days: int,
        month_days: int,
    ) -> Tuple[float, int]:
        accrued_total = sum(
            self.to_float(row.get("use_amount"))
            for row in ncp_service_summary
        )
        current_total = sum(current_by_service.values())
        projected_total = sum(projected_by_service.values())
        if current_total > 0:
            return (
                accrued_total + max(projected_total - current_total, 0.0)
                if accrued_total > 0
                else projected_total,
                0,
            )
        if accrued_total > 0:
            return accrued_total, 1
        return projected_total, 0

    @staticmethod
    def normalize_service_key(value: Any) -> str:
        return "".join(
            character.casefold()
            for character in str(value or "")
            if character.isalnum()
        )

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

    def summarize_contract_demand_by_service(
        self,
        rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        summary = defaultdict(
            lambda: {
                "amount": 0.0,
                "use_amount": 0.0,
                "discount_amount": 0.0,
                "row_count": 0,
            }
        )
        for row in rows:
            service_name = self.get_product_demand_service_name(row)
            if service_name == "UNKNOWN":
                service_name = self.get_usage_service_name(row)
            use_amount = self.to_float(row.get("useAmount"))
            demand_amount = self.to_float(
                self.first_present(
                    row.get("demandAmount"),
                    row.get("useAmount"),
                    default=0,
                )
            )
            summary[service_name]["amount"] += demand_amount
            summary[service_name]["use_amount"] += use_amount
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
        aggregate_groups: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
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

        rating_rows = self.select_active_day_rows(usage_rows, price_map)
        for row in rating_rows:
            price_no = self.get_price_no(row)
            price_row = price_map.get(price_no)

            service_name = self.get_usage_service_name(row)
            item_name = self.get_usage_item_name(row)
            item_code = self.get_usage_item_code(row)
            unit_code = self.get_usage_unit_code(row)
            usage_quantity = self.get_usage_quantity(row)

            if price_row and self.requires_aggregate_rating(price_row):
                aggregate_key = (
                    self._row_member_no(row),
                    price_no,
                    self.get_metering_type_code(row),
                    unit_code,
                )
                aggregate_groups[aggregate_key].append(row)
                continue

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
                self.get_metering_type_code(row),
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

        for key, rows in aggregate_groups.items():
            _, price_no, _, unit_code = key
            price_row = price_map[price_no]
            service_names = sorted({
                self.get_usage_service_name(row) for row in rows
            })
            item_names = sorted({
                self.get_usage_item_name(row) for row in rows
            })
            item_codes = sorted({
                self.get_usage_item_code(row) for row in rows
            })
            service_name = " + ".join(service_names)
            item_name = " + ".join(item_names)
            item_code = " + ".join(item_codes)
            calculated = self.calculate_aggregate_expected_amount(
                rows=rows,
                price_row=price_row,
                days_in_month=days_in_month,
            )
            rating_details = calculated.get("rating_details", {})
            if len(service_names) > 1:
                rating_details = {
                    **rating_details,
                    "aggregated_services": service_names,
                }
            usage_quantity = sum(self.get_usage_quantity(row) for row in rows)
            if usage_quantity == 0 and calculated["expected_amount"] == 0:
                continue
            result.append(
                {
                    "service_name": service_name,
                    "item_name": item_name,
                    "item_code": item_code,
                    "price_no": price_no,
                    "usage_quantity": round(usage_quantity, 6),
                    "unit_code": unit_code,
                    "raw_price": round(self.get_price(price_row), 10),
                    "price_unit_type": self.get_price_unit_type_code(price_row),
                    "charging_unit_type": self.get_charging_unit_type_code(price_row),
                    "unit_price": round(calculated["unit_price"], 10),
                    "multiplier": calculated.get("multiplier", 1.0),
                    "storage_size_gb": round(
                        max((self.get_storage_size_gb(row) for row in rows), default=0.0),
                        6,
                    ),
                    "expected_amount": round(calculated["expected_amount"], 2),
                    "row_count": len(rows),
                    "calculation_method": calculated["calculation_method"],
                    "calculation_status": calculated["calculation_status"],
                    "rating_details": rating_details,
                }
            )

        return sorted(result, key=lambda x: x["expected_amount"], reverse=True)

    def requires_aggregate_rating(self, price_row: Dict[str, Any]) -> bool:
        rating_code = self.get_rating_unit_type_code(price_row)
        if rating_code == "SECT":
            return True
        if self.uses_block_unit_rating(price_row):
            return True
        if self.uses_hour_ceiling_rating(price_row):
            return True
        return (
            self.to_float(price_row.get("freeValue")) > 0
            and not self.has_resource_count_allowance(price_row)
        )

    def uses_block_unit_rating(self, price_row: Dict[str, Any]) -> bool:
        return (
            self.get_charging_unit_type_code(price_row).upper() == "UNITS"
            and self.to_float(price_row.get("chargingUnitBasicValue")) > 1
        )

    def uses_hour_ceiling_rating(self, price_row: Dict[str, Any]) -> bool:
        description = str(price_row.get("priceDescription") or "").upper()
        price_unit = self.get_price_unit_type_code(price_row).upper()
        return (
            self.get_metering_unit_type_code(price_row) == "USAGE_SEC"
            and "USAGE TIME (HOUR)" in description
            and price_unit not in {
                "USAGE_HH", "USAGE_TIME", "HOUR", "HOURLY", "HH",
            }
        )

    def select_active_day_rows(
        self,
        rows: List[Dict[str, Any]],
        price_map: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        regular_rows: List[Dict[str, Any]] = []
        daily_rows: Dict[Tuple[str, ...], Dict[str, Any]] = {}
        daily_prices: Dict[Tuple[str, ...], float] = {}
        for row in rows:
            price_no = self.get_price_no(row)
            price_row = price_map.get(price_no)
            if not price_row or not self.uses_active_day_proration(price_row):
                regular_rows.append(row)
                continue

            identity = self.get_daily_rating_identity(row, price_no)
            effective_price, _ = self.get_effective_price(row, price_row)
            if identity not in daily_rows or effective_price > daily_prices[identity]:
                daily_rows[identity] = row
                daily_prices[identity] = effective_price

        return [*regular_rows, *daily_rows.values()]

    def uses_active_day_proration(self, price_row: Dict[str, Any]) -> bool:
        if self.get_price_type_code(price_row) != "FXSUM":
            return False
        if self.get_rating_unit_type_code(price_row) == "SECT":
            return False
        description = str(price_row.get("priceDescription") or "").upper()
        return "(DAY)" in description or "DAILY CALCULATION" in description

    def is_stateful_projection_price(self, price_row: Dict[str, Any]) -> bool:
        return bool(
            price_row
            and (
                self.uses_active_day_proration(price_row)
                or self.has_resource_count_allowance(price_row)
                or self.get_condition_type_code(price_row) == "SVR_ST_PRC"
            )
        )

    def get_daily_rating_identity(
        self,
        row: Dict[str, Any],
        price_no: str,
    ) -> Tuple[str, ...]:
        contract = self.as_dict(row.get("contract"))
        product = self.as_dict(row.get("contractProduct"))
        use_date = self.as_dict(row.get("useDate"))
        return (
            self._row_member_no(row),
            str(contract.get("contractNo") or ""),
            str(
                product.get("contractProductSequence")
                or product.get("instanceNo")
                or ""
            ),
            price_no,
            str(use_date.get("useStartDate") or ""),
            str(use_date.get("useEndDate") or ""),
        )

    def calculate_aggregate_expected_amount(
        self,
        rows: List[Dict[str, Any]],
        price_row: Dict[str, Any],
        days_in_month: int,
    ) -> Dict[str, Any]:
        if not rows:
            return {
                "expected_amount": 0.0,
                "unit_price": 0.0,
                "calculation_method": "NO_USAGE",
                "calculation_status": "UNSUPPORTED_EMPTY_USAGE_GROUP",
                "multiplier": 1.0,
            }

        rating_code = self.get_rating_unit_type_code(price_row)
        usage_unit_code = self.get_usage_unit_code(rows[0])
        free_value = self.normalize_free_value(
            self.to_float(price_row.get("freeValue")),
            price_row,
            usage_unit_code,
        )

        if self.uses_block_unit_rating(price_row) and rating_code != "SECT":
            quantity = sum(self.get_usage_quantity(row) for row in rows)
            billable_quantity = max(quantity - free_value, 0.0)
            charging_basic_value = self.to_float(
                price_row.get("chargingUnitBasicValue")
            )
            charging_blocks = (
                math.ceil(billable_quantity / charging_basic_value)
                if billable_quantity > 0
                else 0
            )
            price = self.get_price(price_row)
            return {
                "expected_amount": charging_blocks * price,
                "unit_price": price / charging_basic_value,
                "calculation_method": (
                    "CEIL(MONTHLY_AGGREGATE / "
                    "CHARGING_UNIT_BASIC_VALUE) * BLOCK_PRICE"
                ),
                "calculation_status": "OK",
                "multiplier": 1.0,
                "rating_details": {
                    "rated_quantity": round(quantity, 10),
                    "free_quantity": round(free_value, 10),
                    "billable_quantity": round(billable_quantity, 10),
                    "charging_unit_basic_value": charging_basic_value,
                    "charging_blocks": charging_blocks,
                },
            }

        if self.uses_hour_ceiling_rating(price_row) and rating_code != "SECT":
            quantity = sum(self.get_usage_quantity(row) for row in rows)
            billable_quantity = max(quantity - free_value, 0.0)
            rounded_quantity = math.ceil(billable_quantity)
            calculated = self.calculate_expected_amount(
                row=rows[0],
                price_row=price_row,
                usage_quantity=rounded_quantity,
                usage_unit_code=usage_unit_code,
                days_in_month=days_in_month,
            )
            calculated["calculation_method"] = (
                "CEIL(MONTHLY_AGGREGATE_HOUR); "
                f"{calculated['calculation_method']}"
            )
            calculated["rating_details"] = {
                "rated_quantity": round(quantity, 10),
                "free_quantity": round(free_value, 10),
                "billable_quantity": round(billable_quantity, 10),
                "rounded_quantity": rounded_quantity,
            }
            return calculated

        if rating_code == "SECT":
            price_type = self.get_price_type_code(price_row)
            if price_type == "FXSUM":
                quantity = sum(
                    self.monthly_usage_fraction(
                        row,
                        self.get_usage_quantity(row),
                        self.get_usage_unit_code(row),
                        days_in_month,
                    )
                    for row in rows
                )
            else:
                quantity = sum(self.get_usage_quantity(row) for row in rows)
            sections = self.get_period_units(price_row)
            if not sections:
                return {
                    "expected_amount": 0.0,
                    "unit_price": 0.0,
                    "calculation_method": "TIERED_RATING",
                    "calculation_status": "UNSUPPORTED_RATING_SECT_NO_TIERS",
                    "multiplier": 1.0,
                }
            normalized_sections = [
                {
                    "start": self.normalize_rating_boundary(
                        self.to_float(section.get("startValue")),
                        price_row,
                        usage_unit_code,
                    ),
                    "end": (
                        -1.0
                        if self.to_float(section.get("endValue")) == -1
                        else self.normalize_rating_boundary(
                            self.to_float(section.get("endValue")),
                            price_row,
                            usage_unit_code,
                        )
                    ),
                    "price": self.to_float(section.get("price")),
                }
                for section in sections
                if isinstance(section, dict)
            ]
            zero_price_coverage = max(
                (
                    section["end"]
                    for section in normalized_sections
                    if section["price"] == 0
                    and section["start"] == 0
                    and section["end"] >= 0
                ),
                default=0.0,
            )
            duplicate_free_allowance = bool(
                free_value > 0 and zero_price_coverage >= free_value
            )
            effective_free_value = 0.0 if duplicate_free_allowance else free_value
            billable_quantity = max(quantity - effective_free_value, 0.0)
            charging_basic_value = self.to_float(
                price_row.get("chargingUnitBasicValue")
            )
            amount, tier_details = self.apply_tiered_prices(
                billable_quantity,
                normalized_sections,
                charging_basic_value,
            )
            unit_price = amount / billable_quantity if billable_quantity else 0.0
            block_method = (
                " WITH CEILING BLOCKS"
                if charging_basic_value > 1
                else ""
            )
            return {
                "expected_amount": amount,
                "unit_price": unit_price,
                "calculation_method": (
                    "MONTHLY_RESOURCE_FRACTION * TIER_PRICE"
                    if price_type == "FXSUM"
                    else "MONTHLY_AGGREGATE * TIER_PRICE"
                ) + block_method,
                "calculation_status": (
                    "INFERRED" if price_type == "FXSUM" else "OK"
                ),
                "multiplier": 1.0,
                "rating_details": {
                    "rated_quantity": round(quantity, 10),
                    "free_quantity": round(free_value, 10),
                    "effective_free_quantity": round(
                        effective_free_value, 10
                    ),
                    "free_quantity_already_in_tiers": duplicate_free_allowance,
                    "billable_quantity": round(billable_quantity, 10),
                    "charging_unit_basic_value": charging_basic_value,
                    "tiers": tier_details,
                },
            }

        usage_quantity = sum(self.get_usage_quantity(row) for row in rows)
        billable_quantity = max(usage_quantity - free_value, 0.0)
        if any(self.get_storage_size_gb(row) > 0 for row in rows):
            return {
                "expected_amount": 0.0,
                "unit_price": 0.0,
                "calculation_method": "MONTHLY_FREE_ALLOWANCE",
                "calculation_status": "UNSUPPORTED_FREE_STORAGE_RATING",
                "multiplier": 1.0,
            }
        calculated = self.calculate_expected_amount(
            row=rows[0],
            price_row=price_row,
            usage_quantity=billable_quantity,
            usage_unit_code=usage_unit_code,
            days_in_month=days_in_month,
        )
        calculated["calculation_method"] = (
            f"MONTHLY_AGGREGATE - FREE({free_value:g}); "
            f"{calculated['calculation_method']}"
        )
        calculated["rating_details"] = {
            "rated_quantity": round(usage_quantity, 10),
            "free_quantity": round(free_value, 10),
            "billable_quantity": round(billable_quantity, 10),
        }
        return calculated

    @staticmethod
    def get_period_units(price_row: Dict[str, Any]) -> List[Dict[str, Any]]:
        for key in ("periodUnitList", "sectionPriceList"):
            value = price_row.get(key)
            if isinstance(value, list) and value:
                return [item for item in value if isinstance(item, dict)]
        return []

    def normalize_rating_boundary(
        self,
        value: float,
        price_row: Dict[str, Any],
        usage_unit_code: str,
    ) -> float:
        if value in (-1, -1.0):
            return -1.0
        price_unit = self.get_price_unit_type_code(price_row)
        if (
            usage_unit_code in {"GBYTE", "GBYTE_PER_MONTH_DAY"}
            or price_unit in {
                "USAGE_1GB", "AVG_SAVE_CAP_1G", "MMLY_AVG_SAVE_CAP_1G",
                "STRG_1G_MM", "STRG_1G_HH",
            }
        ):
            return value / (1024 ** 3)
        return value

    def normalize_free_value(
        self,
        value: float,
        price_row: Dict[str, Any],
        usage_unit_code: str,
    ) -> float:
        if value <= 0:
            return 0.0
        free_unit = self.get_free_unit_code(price_row)
        if any(token in free_unit for token in ("1G", "GB", "GBYTE")):
            return value
        if "BYTE" in free_unit:
            return value / (1024 ** 3)
        if usage_unit_code in {"GBYTE", "GBYTE_PER_MONTH_DAY"}:
            return value / (1024 ** 3) if value >= 1024 ** 3 else value
        return value

    @staticmethod
    def apply_tiered_prices(
        quantity: float,
        sections: List[Dict[str, float]],
        charging_unit_basic_value: float = 0.0,
    ) -> Tuple[float, List[Dict[str, float]]]:
        amount = 0.0
        details: List[Dict[str, float]] = []
        for section in sorted(sections, key=lambda item: item.get("start", 0.0)):
            start = max(float(section.get("start", 0.0)), 0.0)
            end = float(section.get("end", -1.0))
            price = float(section.get("price", 0.0))
            upper = quantity if end < 0 else min(quantity, end)
            used = max(upper - start, 0.0)
            if used <= 0:
                continue
            charging_units = (
                math.ceil(used / charging_unit_basic_value)
                if charging_unit_basic_value > 1
                else used
            )
            tier_amount = charging_units * price
            amount += tier_amount
            details.append({
                "start": start,
                "end": end,
                "quantity": round(used, 10),
                "charging_units": charging_units,
                "unit_price": price,
                "amount": round(tier_amount, 10),
            })
        return amount, details

    @staticmethod
    def monthly_usage_fraction(
        row: Dict[str, Any],
        usage_quantity: float,
        usage_unit_code: str,
        days_in_month: int,
    ) -> float:
        if usage_unit_code == "HOUR":
            return usage_quantity / (days_in_month * 24)
        if usage_unit_code in {"SEC_DAY", "DAY", "USAGE_DAY"}:
            return usage_quantity / days_in_month
        return usage_quantity

    def calculate_expected_amount(
        self,
        row: Dict[str, Any],
        price_row: Dict[str, Any],
        usage_quantity: float,
        usage_unit_code: str,
        days_in_month: int,
    ) -> Dict[str, Any]:
        price, condition_applied = self.get_effective_price(row, price_row)
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

        price_type_code = self.get_price_type_code(price_row)
        if price_type_code == "FREE":
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
        resource_allowance = self.has_resource_count_allowance(price_row)
        if resource_allowance:
            product_count = self.get_product_count(row)
            if product_count is None:
                return {
                    "expected_amount": 0.0,
                    "unit_price": 0.0,
                    "calculation_method": "FREE_RESOURCE_COUNT",
                    "calculation_status": (
                        "UNSUPPORTED_FREE_RESOURCE_COUNT_MISSING"
                    ),
                    "multiplier": 1.0,
                }
            free_count = self.to_float(price_row.get("freeValue"))
            billable_product_count = max(product_count - free_count, 0.0)
            multiplier *= billable_product_count

        unit_price, method, status = self.resolve_unit_price(
            usage_unit_code=usage_unit_code,
            price_unit_type=price_unit_type,
            price=price,
            days_in_month=days_in_month,
            price_description=str(price_row.get("priceDescription") or ""),
            metering_unit=self.get_metering_unit_type_code(price_row),
        )

        if condition_applied:
            method = f"CONDITION_PRICE; {method}"

        amount = usage_quantity * unit_price

        if self.uses_active_day_proration(price_row) and usage_quantity > 0:
            active_days = self.get_usage_day_count(row, usage_quantity, usage_unit_code)
            unit_price = price / days_in_month
            amount = active_days * unit_price
            method = "ACTIVE_DAY * (MONTH_PRICE / MONTH_DAYS)"
            status = "OK"
            if price_unit_type in ("STRG_1G_HH", "STRG_1G_MM"):
                if storage_size_gb > 0:
                    amount *= storage_size_gb
                    method = f"GB * {method}"
                else:
                    status = "WARN_STORAGE_SIZE_MISSING"
        elif (
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

        if resource_allowance:
            method = (
                f"{method} * BILLABLE_RESOURCE_COUNT"
                f"({billable_product_count:g})"
            )
        elif multiplier != 1:
            method = f"{method} * MULTIPLIER({multiplier})"

        return {
            "expected_amount": amount,
            "unit_price": unit_price,
            "calculation_method": method,
            "calculation_status": status,
            "multiplier": multiplier,
        }

    def get_usage_day_count(
        self,
        row: Dict[str, Any],
        usage_quantity: float,
        usage_unit_code: str,
    ) -> float:
        use_date = self.as_dict(row.get("useDate"))
        start = self._parse_api_date(use_date.get("useStartDate"))
        end = self._parse_api_date(use_date.get("useEndDate"))
        if start and end and end >= start:
            return float((end - start).days + 1)
        if usage_unit_code == "HOUR":
            return usage_quantity / 24
        if usage_unit_code in {"SEC_DAY", "DAY", "USAGE_DAY"}:
            return usage_quantity
        return 1.0

    def get_free_unit_code(self, price_row: Dict[str, Any]) -> str:
        free_unit = self.as_dict(price_row.get("freeUnit"))
        return str(
            self.first_present(
                free_unit.get("code"),
                price_row.get("freeUnitCode"),
                default="",
            )
        ).strip().upper()

    def has_resource_count_allowance(
        self,
        price_row: Dict[str, Any],
    ) -> bool:
        if self.to_float(price_row.get("freeValue")) <= 0:
            return False
        free_unit = self.get_free_unit_code(price_row)
        return "RULE" in free_unit and "CNT" in free_unit

    def get_product_count(self, row: Dict[str, Any]) -> Optional[float]:
        product = self.as_dict(row.get("contractProduct"))
        usage = self.as_dict(row.get("usage"))
        for value in (
            product.get("productCount"),
            product.get("productQuantity"),
            usage.get("productCount"),
            usage.get("productQuantity"),
        ):
            if value not in (None, ""):
                return max(self.to_float(value), 0.0)
        return None

    def get_unsupported_rating_status(
        self,
        price_row: Dict[str, Any],
    ) -> Optional[str]:
        price_type_code = self.get_price_type_code(price_row)
        if price_type_code and price_type_code not in {"FREE", "FXSUM", "MTRAT"}:
            return f"UNSUPPORTED_PRICE_TYPE_{price_type_code}"

        if any(
            isinstance(price_row.get(key), list) and price_row.get(key)
            for key in ("packageUnitList",)
        ):
            return "UNSUPPORTED_RATING_PKG_DIMENSION"
        if any(
            isinstance(price_row.get(key), list) and price_row.get(key)
            for key in ("detailUnitList", "countryUnitList")
        ):
            return "UNSUPPORTED_RATING_DETAIL_DIMENSION"

        rating_code = self.get_rating_unit_type_code(price_row)
        if rating_code == "SECT":
            return f"UNSUPPORTED_RATING_{rating_code}"
        if rating_code in {"PKG", "DETAIL", "CNTRY"}:
            return f"UNSUPPORTED_RATING_{rating_code}_DIMENSION"
        if rating_code and rating_code != "POINT":
            return f"UNSUPPORTED_RATING_{rating_code}"

        return None

    def get_rating_unit_type_code(self, price_row: Dict[str, Any]) -> str:
        rating_unit_type = self.as_dict(price_row.get("ratingUnitType"))
        return str(
            self.first_present(
                rating_unit_type.get("code"),
                price_row.get("ratingUnitTypeCode"),
                default="POINT",
            )
        ).strip().upper()

    def get_effective_price(
        self,
        row: Dict[str, Any],
        price_row: Dict[str, Any],
    ) -> Tuple[float, bool]:
        base_price = self.get_price(price_row)
        condition_code = self.get_condition_type_code(price_row)
        metering_code = self.get_metering_type_code(row)
        metering_name = self.get_metering_type_name(row).upper()
        is_stop_usage = (
            "STOP" in metering_code
            or "STOP" in metering_name
            or metering_code in {"VSVRT", "SVR_STOP"}
        )
        if condition_code == "SVR_ST_PRC" and is_stop_usage:
            return self.to_float(price_row.get("conditionPrice")), True
        return base_price, False

    def get_condition_type_code(self, price_row: Dict[str, Any]) -> str:
        condition_type = self.as_dict(price_row.get("conditionType"))
        return str(
            self.first_present(
                condition_type.get("code"),
                price_row.get("conditionTypeCode"),
                default="",
            )
        ).strip().upper()

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
        price_description: str = "",
        metering_unit: str = "",
    ) -> Tuple[float, str, str]:
        hours_in_month = days_in_month * 24

        if price == 0:
            return 0.0, "ZERO_PRICE", "OK"

        if usage_unit_code == "HOUR" and price_unit_type in ("USAGE_MM", "MONTH", "MONTHLY", "MONT", "MM"):
            return price / hours_in_month, "HOUR * (MONTH_PRICE / MONTH_HOURS)", "OK"

        if usage_unit_code == "HOUR" and price_unit_type in ("USAGE_HH", "HOUR", "HOURLY", "HH"):
            return price, "HOUR * HOUR_PRICE", "OK"

        if usage_unit_code == "HOUR" and price_unit_type in ("USAGE_TIME",):
            return price, "HOUR * HOUR_PRICE", "OK"

        if usage_unit_code == "HOUR" and price_unit_type in (
            "USAGE_MIN", "MINUTE", "MINUTELY", "MI",
        ):
            return price * 60, "HOUR * 60 * MINUTE_PRICE", "OK"

        if usage_unit_code == "HOUR" and price_unit_type in ("DAY", "DAILY", "DD"):
            return price / 24, "HOUR * (DAY_PRICE / 24)", "OK"

        if usage_unit_code == "HOUR" and price_unit_type == "STRG_1G_HH":
            return price, "HOUR * GB_HOUR_PRICE", "OK"

        if usage_unit_code == "HOUR" and price_unit_type == "STRG_1G_MM":
            return price / hours_in_month, "HOUR * (GB_MONTH_PRICE / MONTH_HOURS)", "OK"

        if usage_unit_code in ("SEC_DAY", "DAY", "USAGE_DAY") and price_unit_type in (
            "USAGE_MM", "MONTH", "MONTHLY", "MONT", "MM",
        ):
            return price / days_in_month, "DAY * (MONTH_PRICE / MONTH_DAYS)", "OK"

        if usage_unit_code in ("SEC_DAY", "DAY", "USAGE_DAY") and price_unit_type in (
            "USAGE_HH", "HOUR", "HOURLY", "HH",
        ):
            return price * 24, "DAY * 24 * HOUR_PRICE", "OK"

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

        if usage_unit_code in ("MEMBER", "USER", "USR_CNT") and price_unit_type in (
            "MEMBER", "USER", "USR_CNT",
        ):
            return price, "USER * USER_PRICE", "OK"

        if usage_unit_code == "TOKEN" and price_unit_type in ("REQ_CNT", "TOKEN"):
            return price, "TOKEN * TOKEN_PRICE", "OK"

        if usage_unit_code == "TOKEN" and price_unit_type in ("K_TOKEN", "TOKEN_1000", "1000_TOKEN"):
            return price / 1000, "TOKEN * (PRICE / 1000)", "OK"

        if usage_unit_code == "TOKEN" and price_unit_type in ("M_TOKEN", "TOKEN_1000000", "1000000_TOKEN"):
            return price / 1_000_000, "TOKEN * (PRICE / 1000000)", "OK"

        description = price_description.upper()
        if usage_unit_code == "HOUR" and (
            "USAGE TIME (HOUR)" in description
            or metering_unit == "USAGE_SEC"
        ):
            return price, "HOUR * DESCRIPTION_HOUR_PRICE", "INFERRED"

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

    @staticmethod
    def merge_price_rows(
        fallback_rows: List[Dict[str, Any]],
        requested_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for row in [*fallback_rows, *requested_rows]:
            if not isinstance(row, dict) or not row.get("priceNo"):
                continue
            merged[str(row["priceNo"])] = row
        return list(merged.values())

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

    def get_metering_type_code(self, row: Dict[str, Any]) -> str:
        usage = self.as_dict(row.get("usage"))
        metering_type = self.as_dict(usage.get("meteringType"))
        return str(metering_type.get("code") or "").strip().upper()

    def get_metering_type_name(self, row: Dict[str, Any]) -> str:
        usage = self.as_dict(row.get("usage"))
        metering_type = self.as_dict(usage.get("meteringType"))
        return str(metering_type.get("codeName") or "").strip()

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

    def get_metering_unit_type_code(self, price_row: Dict[str, Any]) -> str:
        metering_unit = self.as_dict(price_row.get("meteringUnit"))
        return str(metering_unit.get("code") or "").strip().upper()

    def get_storage_size_gb(self, row: Dict[str, Any]) -> float:
        contract_product = self.as_dict(row.get("contractProduct"))
        usage = self.as_dict(row.get("usage"))

        # NCP contractProduct productSize values are bytes, including values
        # smaller than 1 GiB (for example a small snapshot).  A magnitude
        # heuristic therefore turns 12 MiB into 12,582,912 GiB.
        byte_candidates = [
            contract_product.get("productSize"),
            contract_product.get("productSizeValue"),
            usage.get("productSize"),
            usage.get("productSizeValue"),
        ]
        for value in byte_candidates:
            size = self.to_float(value)
            if size > 0:
                return size / (1024 ** 3)

        gb_candidates = [
            contract_product.get("storageSizeGb"),
            contract_product.get("diskSizeGb"),
            contract_product.get("blockStorageSizeGb"),
            usage.get("storageSizeGb"),
            usage.get("diskSizeGb"),
            usage.get("blockStorageSizeGb"),
        ]
        for value in gb_candidates:
            size = self.to_float(value)
            if size > 0:
                return size

        ambiguous_candidates = [
            contract_product.get("storageSize"),
            contract_product.get("diskSize"),
            contract_product.get("blockStorageSize"),
            usage.get("storageSize"),
            usage.get("diskSize"),
            usage.get("blockStorageSize"),
        ]

        for value in ambiguous_candidates:
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
