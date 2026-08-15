"""공급자 오류에서 안전한 Sub Account 액션명만 추출한다."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_ACTION_PATTERN = re.compile(
    r"(?:View|Change)/[A-Za-z][A-Za-z0-9_-]{0,99}"
)
_MESSAGE_KEYS = frozenset({
    "message",
    "devmessage",
    "errormessage",
    "description",
})


def extract_required_actions(response: Any) -> tuple[str, ...]:
    """오류 메시지 필드에 직접 포함된 권한 액션만 반환한다.

    응답 전체를 문자열화하지 않으므로 자원명이나 다른 고객 데이터에서
    우연히 액션처럼 보이는 문자열을 권한으로 오인하지 않는다.
    """

    payload = _response_payload(response)
    messages: list[str] = []
    _collect_messages(payload, messages, depth=0)
    return tuple(dict.fromkeys(
        action
        for message in messages
        for action in _ACTION_PATTERN.findall(message)
    ))


def extract_provider_code(response: Any) -> str | None:
    """Return the first non-success provider code from a response payload."""

    return _find_provider_code(_response_payload(response), depth=0)


def _response_payload(response: Any) -> Any:
    if isinstance(response, (Mapping, list, tuple)):
        return response
    json_method = getattr(response, "json", None)
    if not callable(json_method):
        return None
    try:
        return json_method()
    except (TypeError, ValueError):
        return None


def _find_provider_code(value: Any, depth: int) -> str | None:
    if depth > 4 or not isinstance(value, Mapping):
        return None
    for key in ("errorCode", "code", "returnCode"):
        candidate = value.get(key)
        if candidate not in (None, "", 0, "0", 200, "200"):
            return str(candidate)[:100]
    for child in value.values():
        if isinstance(child, Mapping):
            candidate = _find_provider_code(child, depth + 1)
            if candidate:
                return candidate
    return None


def _collect_messages(value: Any, output: list[str], depth: int) -> None:
    if depth > 5:
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if (
                str(key).replace("_", "").casefold() in _MESSAGE_KEYS
                and isinstance(item, str)
            ):
                output.append(item[:4_000])
            elif isinstance(item, (Mapping, list, tuple)):
                _collect_messages(item, output, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value[:100]:
            _collect_messages(item, output, depth + 1)


__all__ = ["extract_provider_code", "extract_required_actions"]
