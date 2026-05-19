"""공통 API 유틸리티.

각 API 클래스에서 반복되는 파라미터 구성 로직을 단순화합니다.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional


class APIParamBuilder:
    """NCP API용 파라미터 빌더."""

    def __init__(self, initial: Optional[Mapping[str, Any]] = None):
        self.params: Dict[str, Any] = {}
        if initial:
            for k, v in initial.items():
                if v is not None:
                    self.params[k] = v

    def add(self, key: str, value: Any) -> "APIParamBuilder":
        if value is not None:
            self.params[key] = value
        return self

    def add_many(self, mapping: Mapping[str, Any]) -> "APIParamBuilder":
        for key, value in mapping.items():
            self.add(key, value)
        return self

    def add_indexed(self, prefix: str, values: Optional[Iterable[Any]]) -> "APIParamBuilder":
        if values is None:
            return self
        for idx, value in enumerate(values, start=1):
            self.params[f"{prefix}.{idx}"] = value
        return self

    def build(self) -> Dict[str, Any]:
        return dict(self.params)
