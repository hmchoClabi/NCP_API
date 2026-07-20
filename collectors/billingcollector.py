from typing import Any, Callable, Dict, List, Optional


class BillingCollector:
    def __init__(self, api_factory: Any):
        self.api_factory = api_factory
        self.platform_api = self.api_factory.get("platform")

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
    ) -> Dict[str, Any]:

        common_params = {
            "member_no_list": member_no_list,
            "is_organization": is_organization,
            "is_parent": is_parent,
        }

        raw: Dict[str, Any] = {}

        raw["demand_cost"] = self.collect_paged(
            self.platform_api.get_demand_cost_list,
            start_month=demand_month,
            end_month=demand_month,
            **common_params,
        )

        raw["product_demand_cost"] = self.collect_paged(
            self.platform_api.get_product_demand_cost_list,
            start_month=demand_month,
            end_month=demand_month,
            **common_params,
        )

        raw["contract_demand_cost"] = self.collect_paged(
            self.platform_api.get_contract_demand_cost_list,
            start_month=demand_month,
            end_month=demand_month,
            region_code=region_code,
            **common_params,
        )

        raw["daily_usage"] = self.collect_paged(
            self.platform_api.get_contract_usage_list_by_daily,
            use_start_date=use_start_date,
            use_end_date=use_end_date,
            region_code=region_code,
            **common_params,
        )

        raw["contract_usage"] = self.collect_paged(
            self.platform_api.get_contract_usage_list,
            start_month=demand_month,
            end_month=demand_month,
            region_code=region_code,
            **common_params,
        )

        price_no_list = self.extract_price_no_list(raw["daily_usage"])

        raw["price_list"] = self.collect_price_list(
            price_no_list=price_no_list,
            pay_currency_code=pay_currency_code,
        )

        raw["product_price_list"] = self.collect_paged(
            self.platform_api.get_product_price_list,
            region_code=region_code,
            pay_currency_code=pay_currency_code,
        )

        raw["product_demand_cost_by_discount"] = self.collect_paged(
            self.platform_api.get_product_demand_cost_by_discount_list,
            start_month=demand_month,
            end_month=demand_month,
            **common_params,
        )

        raw["discount_list"] = self.collect_paged(
            self.platform_api.get_discount_list,
            start_month=demand_month,
            end_month=demand_month,
            is_valid_discount=False,
            **common_params,
        )

        discount_no_list = self.extract_discount_no_list(raw["discount_list"])

        raw["credit_history"] = self.collect_credit_history(
            demand_month=demand_month,
            discount_no_list=discount_no_list,
            **common_params,
        )

        raw["product_discount_history"] = self.collect_product_discount_history(
            demand_month=demand_month,
            discount_no_list=discount_no_list,
            **common_params,
        )

        raw["coin_history"] = self.collect_coin_history(
            discount_no_list=discount_no_list,
            **common_params,
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
        }

        return raw

    def collect_paged(
        self,
        func: Callable[..., Dict[str, Any]],
        page_size: int = 1000,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        pages: List[Dict[str, Any]] = []
        page_no = 1

        while True:
            response = func(
                page_no=page_no,
                page_size=page_size,
                **kwargs,
            )

            pages.append(response)

            total_rows = self.find_first_value(response, "totalRows")

            if not total_rows:
                break

            if page_no * page_size >= int(total_rows):
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
            pages.append(
                self.platform_api.get_price_list(
                    price_no_list=chunk,
                    pay_currency_code=pay_currency_code,
                )
            )

        return pages

    def collect_credit_history(
        self,
        demand_month: str,
        discount_no_list: List[str],
        **kwargs,
    ) -> List[Dict[str, Any]]:
        if not discount_no_list:
            return []

        return self.collect_paged(
            self.platform_api.get_credit_history_list,
            start_month=demand_month,
            end_month=demand_month,
            discount_no_list=discount_no_list,
            **kwargs,
        )

    def collect_product_discount_history(
        self,
        demand_month: str,
        discount_no_list: List[str],
        **kwargs,
    ) -> List[Dict[str, Any]]:
        if not discount_no_list:
            return []

        return self.collect_paged(
            self.platform_api.get_product_discount_history_list,
            start_month=demand_month,
            end_month=demand_month,
            discount_no_list=discount_no_list,
            **kwargs,
        )

    def collect_coin_history(
        self,
        discount_no_list: List[str],
        **kwargs,
    ) -> List[Dict[str, Any]]:
        if not discount_no_list:
            return []

        return [
            self.platform_api.get_coin_history_list(
                discount_no_list=discount_no_list,
                **kwargs,
            )
        ]

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
        for idx in range(0, len(values), size):
            yield values[idx:idx + size]