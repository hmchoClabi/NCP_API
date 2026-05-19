"""공통 API 유틸리티.

각 API 클래스에서 반복되는 파라미터 구성 로직을 단순화합니다.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Sequence


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

    def add_indexed_objects(
        self,
        prefix: str,
        items: Optional[Iterable[Mapping[str, Any]]],
    ) -> "APIParamBuilder":
        """Add list-of-object parameters such as sortList.1.sortedBy."""
        if items is None:
            return self
        for idx, item in enumerate(items, start=1):
            for key, value in item.items():
                if value is not None:
                    self.params[f"{prefix}.{idx}.{key}"] = value
        return self

    def add_indexed_parallel(
        self,
        prefix: str,
        field_names: Sequence[str],
        value_lists: Sequence[Sequence[Any]],
    ) -> "APIParamBuilder":
        """Add indexed object params from parallel lists."""
        if not field_names or not value_lists:
            return self
        if len(field_names) != len(value_lists):
            raise ValueError("field_names와 value_lists 길이가 같아야 합니다.")

        lengths = [len(values) for values in value_lists]
        if len(set(lengths)) != 1:
            raise ValueError("value_lists의 각 리스트 길이가 같아야 합니다.")

        for idx, values in enumerate(zip(*value_lists), start=1):
            for field_name, value in zip(field_names, values):
                if value is not None:
                    self.params[f"{prefix}.{idx}.{field_name}"] = value
        return self

    def build(self) -> Dict[str, Any]:
        return dict(self.params)
