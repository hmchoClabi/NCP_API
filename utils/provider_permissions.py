"""공급자 오류에서 안전한 Sub Account 액션명만 추출한다."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_ACTION_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])(?:View|Change)/[A-Za-z][A-Za-z0-9_-]{0,99}"
    r"(?![A-Za-z0-9_-])"
)
_CODE_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,100}")
_ROOT_MESSAGE_KEYS = frozenset(
    {
        "message",
        "devmessage",
        "errormessage",
    }
)
_ERROR_MESSAGE_KEYS = _ROOT_MESSAGE_KEYS | {"description", "returnmessage"}
_ERROR_ENVELOPE_KEYS = frozenset({"error", "errors", "responseerror"})


def extract_required_actions(response: Any) -> tuple[str, ...]:
    """오류 메시지 필드에 직접 포함된 권한 액션만 반환한다.

    응답 전체를 문자열화하지 않으므로 자원명이나 다른 고객 데이터에서
    우연히 액션처럼 보이는 문자열을 권한으로 오인하지 않는다.
    """

    payload = _response_payload(response)
    messages: list[str] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if _normalized_key(key) in _ERROR_ENVELOPE_KEYS:
                _collect_error_messages(value, messages, depth=0)
        if _is_error_response(response, payload):
            _append_message_fields(payload, messages, _ERROR_MESSAGE_KEYS)
    return tuple(
        dict.fromkeys(action for message in messages for action in _ACTION_PATTERN.findall(message))
    )


def extract_provider_code(response: Any) -> str | None:
    """Return the first non-success provider code from a response payload."""

    payload = _response_payload(response)
    if not isinstance(payload, Mapping):
        return _find_specific_provider_code(payload, depth=0)
    for key in ("errorCode", "returnCode"):
        candidate = _normalize_provider_code(payload.get(key))
        if candidate:
            return candidate
    for key, value in payload.items():
        if _normalized_key(key) in _ERROR_ENVELOPE_KEYS:
            candidate = _find_specific_provider_code(value, depth=0)
            if candidate:
                return candidate
    for key, value in payload.items():
        if _normalized_key(key) in _ERROR_ENVELOPE_KEYS:
            candidate = _find_generic_provider_code(value, depth=0)
            if candidate:
                return candidate
    candidate = _find_specific_provider_code(payload, depth=0)
    if candidate:
        return candidate
    return _normalize_provider_code(payload.get("code"))


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


def _is_error_response(response: Any, payload: Mapping[Any, Any]) -> bool:
    try:
        if int(getattr(response, "status_code")) >= 400:
            return True
    except (AttributeError, TypeError, ValueError):
        pass
    if any(_normalized_key(key) in _ERROR_ENVELOPE_KEYS for key in payload):
        return True
    return any(_normalize_provider_code(payload.get(key)) for key in ("errorCode", "returnCode"))


def _find_specific_provider_code(value: Any, depth: int) -> str | None:
    if depth > 5:
        return None
    if isinstance(value, Mapping):
        for key in ("errorCode", "returnCode"):
            candidate = _normalize_provider_code(value.get(key))
            if candidate:
                return candidate
        children = value.values()
    elif isinstance(value, (list, tuple)):
        children = value[:100]
    else:
        return None
    for child in children:
        if isinstance(child, (Mapping, list, tuple)):
            candidate = _find_specific_provider_code(child, depth + 1)
            if candidate:
                return candidate
    return None


def _find_generic_provider_code(value: Any, depth: int) -> str | None:
    if depth > 5:
        return None
    if isinstance(value, Mapping):
        candidate = _normalize_provider_code(value.get("code"))
        if candidate:
            return candidate
        children = value.values()
    elif isinstance(value, (list, tuple)):
        children = value[:100]
    else:
        return None
    for child in children:
        if isinstance(child, (Mapping, list, tuple)):
            candidate = _find_generic_provider_code(child, depth + 1)
            if candidate:
                return candidate
    return None


def _normalize_provider_code(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    candidate = str(value)
    if candidate in {"", "0", "200"}:
        return None
    return candidate if _CODE_PATTERN.fullmatch(candidate) else None


def _normalized_key(value: Any) -> str:
    return str(value).replace("_", "").casefold()


def _append_message_fields(
    value: Mapping[Any, Any],
    output: list[str],
    allowed_keys: frozenset[str],
) -> None:
    for key, item in value.items():
        if _normalized_key(key) in allowed_keys and isinstance(item, str):
            output.append(item[:4_000])


def _collect_error_messages(
    value: Any,
    output: list[str],
    depth: int,
    *,
    trusted: bool = True,
) -> None:
    if depth > 5:
        return
    if isinstance(value, Mapping):
        if trusted:
            _append_message_fields(value, output, _ERROR_MESSAGE_KEYS)
        for key, item in value.items():
            if isinstance(item, (Mapping, list, tuple)):
                _collect_error_messages(
                    item,
                    output,
                    depth + 1,
                    trusted=(_normalized_key(key) in _ERROR_ENVELOPE_KEYS),
                )
    elif isinstance(value, (list, tuple)):
        for item in value[:100]:
            _collect_error_messages(
                item,
                output,
                depth + 1,
                trusted=trusted,
            )


__all__ = ["extract_provider_code", "extract_required_actions"]
