"""수집기가 HTTP 200 오류/비정상 응답을 빈 결과로 오인하지 않게 한다."""

from typing import Any, Iterable


class APIResponseValidationError(ValueError):
    """API 응답이 예상한 수집 응답 계약을 만족하지 않을 때 발생한다."""


def validate_collection_response(
    response: Any,
    *,
    expected_keys: Iterable[str],
    allow_list: bool = False,
    api_name: str = "API",
) -> None:
    """알려진 오류 envelope와 예상하지 못한 응답 구조를 거부한다.

    개별 항목의 일부 필드가 잘못된 경우는 기존 정규화 단계가 처리하도록
    허용하되, 응답 전체가 오류이거나 예상 collection key가 없는 경우에는
    빈 정상 응답으로 취급하지 않는다.
    """

    if isinstance(response, list):
        if allow_list:
            return
        raise APIResponseValidationError(
            f"{api_name} 응답이 예상한 object 형식이 아닙니다."
        )

    if not isinstance(response, dict):
        raise APIResponseValidationError(
            f"{api_name} 응답이 object 형식이 아닙니다."
        )

    _raise_for_nested_error_envelopes(response, api_name=api_name)

    for key in ("data", "result", "response"):
        nested = response.get(key)
        if allow_list and isinstance(nested, list):
            return

    expected = tuple(expected_keys)
    if _contains_expected_key(response, expected):
        return

    expected_text = ", ".join(expected)
    raise APIResponseValidationError(
        f"{api_name} 응답에 예상 필드가 없습니다: {expected_text}"
    )


def _contains_expected_key(
    value: Any,
    expected_keys: tuple[str, ...],
    depth: int = 0,
) -> bool:
    if depth > 5:
        return False

    if isinstance(value, dict):
        if any(key in value for key in expected_keys):
            return True
        return any(
            _contains_expected_key(child, expected_keys, depth + 1)
            for child in value.values()
            if isinstance(child, (dict, list))
        )

    if isinstance(value, list):
        return any(
            _contains_expected_key(child, expected_keys, depth + 1)
            for child in value
            if isinstance(child, (dict, list))
        )

    return False


def _raise_for_nested_error_envelopes(
    response: dict[str, Any],
    *,
    api_name: str,
    depth: int = 0,
) -> None:
    if depth > 5:
        return

    _raise_for_error_envelope(response, api_name=api_name)

    # collection 항목 목록 내부의 업무 데이터까지 오류 envelope로 오인하지
    # 않도록 object wrapper만 순회한다.
    for child in response.values():
        if isinstance(child, dict):
            _raise_for_nested_error_envelopes(
                child,
                api_name=api_name,
                depth=depth + 1,
            )


def _raise_for_error_envelope(
    response: dict[str, Any],
    *,
    api_name: str,
) -> None:
    error = response.get("error")
    error_code = response.get("errorCode")

    if error:
        if isinstance(error, dict):
            error_code = (
                error.get("errorCode")
                or error.get("code")
                or error_code
            )
        raise APIResponseValidationError(
            _error_message(api_name, error_code)
        )

    if error_code not in (None, "", 0, "0"):
        raise APIResponseValidationError(
            _error_message(api_name, error_code)
        )

    return_code = response.get("returnCode")
    if return_code not in (None, "", 0, "0", 200, "200"):
        raise APIResponseValidationError(
            _error_message(api_name, return_code)
        )

    status_code = response.get("status_code", response.get("statusCode"))
    try:
        is_error_status = (
            status_code is not None
            and int(status_code) >= 400
        )
    except (TypeError, ValueError):
        is_error_status = False

    if is_error_status:
        raise APIResponseValidationError(
            _error_message(api_name, status_code)
        )


def _error_message(api_name: str, code: Any) -> str:
    if code in (None, ""):
        return f"{api_name} 오류 응답을 받았습니다."

    safe_code = "".join(
        character
        for character in str(code)[:64]
        if character.isalnum() or character in {"-", "_", "."}
    )
    if not safe_code:
        return f"{api_name} 오류 응답을 받았습니다."
    return f"{api_name} 오류 응답을 받았습니다 (code={safe_code})."
