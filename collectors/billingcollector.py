from typing import Any, Callable, Dict, List, Optional

import requests

from utils.common_rest import safe_exception_message
from utils.response_validation import validate_collection_response


class BillingCollector:
    MAX_PAGES = 10_000
    DISCOUNT_SOURCES = frozenset({
        "product_demand_cost_by_discount",
        "discount_list",
        "credit_history",
        "product_discount_history",
        "coin_history",
    })

    def __init__(self, api_factory: Any):
        self.api_factory = api_factory
        self.platform_api = self.api_factory.get("platform")
        self.last_errors: List[Dict[str, Any]] = []
        self.last_warnings: List[Dict[str, Any]] = []

    def collect_raw(
        self,
        use_start_date: str,
        use_end_date: str,
        demand_month: str,
        region_code: str = "KR",
        pay_currency_code: str = "KRW",
        member_no_list: Optional[List[str]] = None,
        is_organization: Optional[bool] = None,
        is_parent: Optional[bool] = None,
        confirmed_demand_month: Optional[str] = None,
        month_to_date_start: Optional[str] = None,
        month_to_date_end: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.last_errors = []
        self.last_warnings = []
        confirmed_demand_month = confirmed_demand_month or demand_month

        common_params = {
            "member_no_list": member_no_list,
            "is_organization": is_organization,
            "is_parent": is_parent,
        }

        raw: Dict[str, Any] = {}

        raw["demand_cost"] = self._collect_paged_source(
            source="demand_cost",
            func=self.platform_api.get_demand_cost_list,
            expected_keys=("demandCostList",),
            start_month=demand_month,
            end_month=demand_month,
            **common_params,
        )

        raw["product_demand_cost"] = self._collect_paged_source(
            source="product_demand_cost",
            func=self.platform_api.get_product_demand_cost_list,
            expected_keys=("productDemandCostList",),
            comparison_required=True,
            start_month=demand_month,
            end_month=demand_month,
            **common_params,
        )

        raw["contract_demand_cost"] = self._collect_paged_source(
            source="contract_demand_cost",
            func=self.platform_api.get_contract_demand_cost_list,
            expected_keys=("contractDemandCostList", "ContractDemandCostList"),
            start_month=demand_month,
            end_month=demand_month,
            region_code=region_code,
            **common_params,
        )

        raw["daily_usage"] = self._collect_paged_source(
            source="daily_usage",
            func=self.platform_api.get_contract_usage_list_by_daily,
            expected_keys=("contractUsageListByDaily",),
            comparison_required=True,
            use_start_date=use_start_date,
            use_end_date=use_end_date,
            region_code=region_code,
            **common_params,
        )

        if month_to_date_start and month_to_date_end:
            raw["month_to_date_usage"] = self._collect_paged_source(
                source="month_to_date_usage",
                func=self.platform_api.get_contract_usage_list_by_daily,
                expected_keys=("contractUsageListByDaily",),
                use_start_date=month_to_date_start,
                use_end_date=month_to_date_end,
                region_code=region_code,
                **common_params,
            )
        else:
            raw["month_to_date_usage"] = []

        raw["contract_usage"] = self._collect_paged_source(
            source="contract_usage",
            func=self.platform_api.get_contract_usage_list,
            expected_keys=("contractList",),
            start_month=demand_month,
            end_month=demand_month,
            region_code=region_code,
            **common_params,
        )

        price_no_list = sorted(set(
            self.extract_price_no_list(raw["daily_usage"])
            + self.extract_price_no_list(raw["month_to_date_usage"])
        ))

        raw["price_list"] = self._collect_source(
            source="price_list",
            operation=lambda: self.collect_price_list(
                price_no_list=price_no_list,
                pay_currency_code=pay_currency_code,
            ),
            comparison_required=True,
        )

        raw["product_price_list"] = self._collect_paged_source(
            source="product_price_list",
            func=self.platform_api.get_product_price_list,
            expected_keys=("productPriceList",),
            region_code=region_code,
            pay_currency_code=pay_currency_code,
        )

        if confirmed_demand_month == demand_month:
            raw["confirmed_demand_cost"] = raw["demand_cost"]
            raw["confirmed_product_demand_cost"] = raw["product_demand_cost"]
        else:
            raw["confirmed_demand_cost"] = self._collect_paged_source(
                source="confirmed_demand_cost",
                func=self.platform_api.get_demand_cost_list,
                expected_keys=("demandCostList",),
                start_month=confirmed_demand_month,
                end_month=confirmed_demand_month,
                **common_params,
            )
            raw["confirmed_product_demand_cost"] = self._collect_paged_source(
                source="confirmed_product_demand_cost",
                func=self.platform_api.get_product_demand_cost_list,
                expected_keys=("productDemandCostList",),
                comparison_required=True,
                start_month=confirmed_demand_month,
                end_month=confirmed_demand_month,
                **common_params,
            )

        raw["product_demand_cost_by_discount"] = self._collect_paged_source(
            source="product_demand_cost_by_discount",
            func=self.platform_api.get_product_demand_cost_by_discount_list,
            expected_keys=("productDemandCostByDiscountList",),
            start_month=demand_month,
            end_month=demand_month,
            **common_params,
        )

        raw["discount_list"] = self._collect_paged_source(
            source="discount_list",
            func=self.platform_api.get_discount_list,
            expected_keys=("discountList",),
            start_month=demand_month,
            end_month=demand_month,
            is_valid_discount=False,
            **common_params,
        )

        discount_no_list = self.extract_discount_no_list(raw["discount_list"])

        raw["credit_history"] = self._collect_source(
            source="credit_history",
            operation=lambda: self.collect_credit_history(
                demand_month=demand_month,
                discount_no_list=discount_no_list,
                **common_params,
            ),
        )

        raw["product_discount_history"] = self._collect_source(
            source="product_discount_history",
            operation=lambda: self.collect_product_discount_history(
                demand_month=demand_month,
                discount_no_list=discount_no_list,
                **common_params,
            ),
        )

        raw["coin_history"] = self._collect_source(
            source="coin_history",
            operation=lambda: self.collect_coin_history(
                discount_no_list=discount_no_list,
                **common_params,
            ),
        )

        raw["_meta"] = {
            "demand_month": demand_month,
            "use_start_date": use_start_date,
            "use_end_date": use_end_date,
            "region_code": region_code,
            "pay_currency_code": pay_currency_code,
            "price_no_count": len(price_no_list),
            "discount_no_count": len(discount_no_list),
            "price_no_list": price_no_list,
            "discount_no_list": discount_no_list,
            "collection_errors": list(self.last_errors),
            "collection_warnings": list(self.last_warnings),
            "confirmed_demand_month": confirmed_demand_month,
            "month_to_date_start": month_to_date_start,
            "month_to_date_end": month_to_date_end,
        }

        return raw

    def _collect_paged_source(
        self,
        *,
        source: str,
        func: Callable[..., Dict[str, Any]],
        expected_keys: tuple[str, ...],
        comparison_required: bool = False,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        return self._collect_source(
            source=source,
            comparison_required=comparison_required,
            operation=lambda: self._collect_and_validate_pages(
                source=source,
                func=func,
                expected_keys=expected_keys,
                **kwargs,
            ),
        )

    def _collect_and_validate_pages(
        self,
        *,
        source: str,
        func: Callable[..., Dict[str, Any]],
        expected_keys: tuple[str, ...],
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        pages = self.collect_paged(func, **kwargs)
        for response in pages:
            validate_collection_response(
                response,
                expected_keys=expected_keys,
                api_name=source,
            )
        return pages

    def _collect_source(
        self,
        *,
        source: str,
        operation: Callable[[], List[Dict[str, Any]]],
        comparison_required: bool = False,
    ) -> List[Dict[str, Any]]:
        try:
            return operation()
        except Exception as exc:
            issue = {
                "collector": self.__class__.__name__,
                "stage": "collection",
                "target_type": "billing",
                "api": source,
                "source": source,
                "comparison_required": comparison_required,
                "exception_type": type(exc).__name__,
                "message": safe_exception_message(exc),
            }
            discount_response = self._discount_unavailable_response(exc)
            if source in self.DISCOUNT_SOURCES and discount_response:
                issue.update(discount_response)
                issue["severity"] = "WARNING"
                issue["message"] = (
                    "NCP 계정에서 Discount API를 사용할 수 없습니다 "
                    "(returnCode 2300). 할인 합계는 청구 비용 데이터로 표시하며 "
                    "할인 상세 이력은 제외합니다."
                )
                self.last_warnings.append(issue)
            else:
                self.last_errors.append(issue)
            return []

    def _discount_unavailable_response(
        self, exc: Exception
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(exc, requests.HTTPError) or exc.response is None:
            return None
        try:
            payload = exc.response.json()
        except (ValueError, TypeError):
            return None
        return_code = self.find_first_value(payload, "returnCode")
        if str(return_code) != "2300":
            return None
        request_id = self.find_first_value(payload, "requestId")
        return {
            "status_code": exc.response.status_code,
            "error_code": "2300",
            "return_message": str(
                self.find_first_value(payload, "returnMessage") or ""
            )[:500],
            "request_id": str(request_id)[:100] if request_id else None,
            "retryable": False,
        }

    def collect_paged(
        self,
        func: Callable[..., Dict[str, Any]],
        page_size: int = 1000,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        if page_size <= 0:
            raise ValueError("page_size는 1 이상이어야 합니다.")

        pages: List[Dict[str, Any]] = []
        page_no = 1

        while True:
            if page_no > self.MAX_PAGES:
                raise RuntimeError(
                    f"Billing API 페이지 수가 안전 한도({self.MAX_PAGES})를 초과했습니다."
                )

            response = func(
                page_no=page_no,
                page_size=page_size,
                **kwargs,
            )
            if not isinstance(response, dict):
                raise TypeError(
                    "Billing API 페이지 응답은 dict여야 합니다: "
                    f"page_no={page_no}, type={type(response).__name__}"
                )

            pages.append(response)

            total_rows = self.find_first_value(response, "totalRows")

            if total_rows in (None, ""):
                break

            try:
                total_rows_int = int(total_rows)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"유효하지 않은 totalRows 값입니다: {total_rows!r}"
                ) from exc

            if total_rows_int < 0:
                raise ValueError(f"totalRows는 음수일 수 없습니다: {total_rows_int}")

            if page_no * page_size >= total_rows_int:
                break

            page_no += 1

        return pages

    def collect_price_list(
        self,
        price_no_list: List[str],
        pay_currency_code: str = "KRW",
    ) -> List[Dict[str, Any]]:
        if not price_no_list:
            return []

        pages: List[Dict[str, Any]] = []

        for chunk in self.chunk(price_no_list, 99):
            response = self.platform_api.get_price_list(
                price_no_list=chunk,
                pay_currency_code=pay_currency_code,
            )
            validate_collection_response(
                response,
                expected_keys=("priceList",),
                api_name="price_list",
            )
            pages.append(response)

        return pages

    def collect_credit_history(
        self,
        demand_month: str,
        discount_no_list: List[str],
        **kwargs,
    ) -> List[Dict[str, Any]]:
        if not discount_no_list:
            return []

        pages = self.collect_paged(
            self.platform_api.get_credit_history_list,
            start_month=demand_month,
            end_month=demand_month,
            discount_no_list=discount_no_list,
            **kwargs,
        )
        self._validate_page_list(
            pages,
            expected_keys=("creditHistoryList",),
            api_name="credit_history",
        )
        return pages

    def collect_product_discount_history(
        self,
        demand_month: str,
        discount_no_list: List[str],
        **kwargs,
    ) -> List[Dict[str, Any]]:
        if not discount_no_list:
            return []

        pages = self.collect_paged(
            self.platform_api.get_product_discount_history_list,
            start_month=demand_month,
            end_month=demand_month,
            discount_no_list=discount_no_list,
            **kwargs,
        )
        self._validate_page_list(
            pages,
            expected_keys=("productDiscountHistoryList",),
            api_name="product_discount_history",
        )
        return pages

    def collect_coin_history(
        self,
        discount_no_list: List[str],
        **kwargs,
    ) -> List[Dict[str, Any]]:
        if not discount_no_list:
            return []

        pages = self.collect_paged(
            self.platform_api.get_coin_history_list,
            discount_no_list=discount_no_list,
            **kwargs,
        )
        self._validate_page_list(
            pages,
            expected_keys=("coinHistoryList",),
            api_name="coin_history",
        )
        return pages

    def _validate_page_list(
        self,
        pages: List[Dict[str, Any]],
        *,
        expected_keys: tuple[str, ...],
        api_name: str,
    ) -> None:
        for response in pages:
            validate_collection_response(
                response,
                expected_keys=expected_keys,
                api_name=api_name,
            )

    def extract_price_no_list(
        self,
        pages: List[Dict[str, Any]],
    ) -> List[str]:
        rows = self.find_first_list(
            pages,
            "contractUsageListByDaily",
        )

        result = set()

        for row in rows:
            price_no = (
                row.get("contractProduct", {})
                .get("priceNo")
            )

            if price_no:
                result.add(str(price_no))

        return sorted(result)

    def extract_discount_no_list(
        self,
        pages: List[Dict[str, Any]],
    ) -> List[str]:
        rows = self.find_first_list(
            pages,
            "discountList",
        )

        result = set()

        for row in rows:
            discount_no = row.get("discountNo")

            if discount_no:
                result.add(str(discount_no))

        return sorted(result)

    def find_first_list(
        self,
        value: Any,
        target_key: str,
    ) -> List[Any]:
        result: List[Any] = []

        if isinstance(value, dict):
            if isinstance(value.get(target_key), list):
                result.extend(value[target_key])

            for child in value.values():
                result.extend(
                    self.find_first_list(
                        child,
                        target_key,
                    )
                )

        elif isinstance(value, list):
            for item in value:
                result.extend(
                    self.find_first_list(
                        item,
                        target_key,
                    )
                )

        return result

    def find_first_value(
        self,
        value: Any,
        target_key: str,
    ):
        if isinstance(value, dict):
            if target_key in value:
                return value[target_key]

            for child in value.values():
                found = self.find_first_value(
                    child,
                    target_key,
                )

                if found is not None:
                    return found

        elif isinstance(value, list):
            for item in value:
                found = self.find_first_value(
                    item,
                    target_key,
                )

                if found is not None:
                    return found

        return None

    def chunk(
        self,
        values: List[str],
        size: int,
    ):
        if size <= 0:
            raise ValueError("chunk size는 1 이상이어야 합니다.")
        for idx in range(0, len(values), size):
            yield values[idx:idx + size]
