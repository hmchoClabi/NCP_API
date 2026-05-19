"""ncp_api 공통 베이스 클래스.

중복되는 파라미터 조립 및 요청 호출 패턴을 공통화합니다.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from utils.api_base import APIParamBuilder
from utils.common_rest import NCPBaseClient


class BaseNCPAPI:
    """모든 ncp_api 모듈이 상속받는 공통 베이스 클래스."""

    def __init__(self, client: NCPBaseClient):
        self.client = client

    @staticmethod
    def build_params(initial: Optional[Dict[str, Any]] = None) -> APIParamBuilder:
        return APIParamBuilder(initial)

    @staticmethod
    def add_indexed(params: Dict[str, Any], prefix: str, values: Optional[Iterable[Any]]) -> Dict[str, Any]:
        if values is None:
            return params
        for idx, value in enumerate(values, start=1):
            params[f"{prefix}.{idx}"] = value
        return params

    def get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.client.get(endpoint, params=params)

    def post(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any] | list] = None,
    ) -> Dict[str, Any]:
        return self.client.post(endpoint, params=params, json_data=json_data)
