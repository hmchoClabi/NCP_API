"""
RESTful API 공용 클라이언트 모듈

모든 HTTP 메서드와 파라미터 타입을 지원하는 범용 API 클라이언트입니다.
"""

import json
import logging
import numbers
import time
from collections.abc import Mapping
from typing import Any, Dict, List, Optional, Union
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from config.settings import API_RETRY_COUNT, API_TIMEOUT
from ncp_api.auth import NCPAuth

logger = logging.getLogger(__name__)

_REDACTED = "***REDACTED***"
_SENSITIVE_KEY_NAMES = {
    "authorization",
    "credential",
    "credentials",
    "cookie",
    "key",
    "password",
    "passwd",
    "secret",
    "setcookie",
    "token",
}
_SENSITIVE_KEY_FRAGMENTS = (
    "accesskey",
    "apikey",
    "authorization",
    "credential",
    "privatekey",
    "secret",
    "signature",
    "token",
)
_RETRYABLE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})


def _normalized_key(value: Any) -> str:
    return "".join(character for character in str(value).lower() if character.isalnum())


def _is_sensitive_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    return normalized in _SENSITIVE_KEY_NAMES or any(
        fragment in normalized for fragment in _SENSITIVE_KEY_FRAGMENTS
    )


def _redact_value(value: Any) -> Any:
    """로그용 데이터에서 자격 증명으로 보이는 값을 재귀적으로 제거합니다."""
    if isinstance(value, Mapping):
        return {
            key: _REDACTED if _is_sensitive_key(key) else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{type(value).__name__} length={len(value)}>"
    if isinstance(value, str):
        # 구조를 알 수 없는 raw 문자열은 일부만 출력해도 비밀이 노출될 수 있습니다.
        return f"<str length={len(value)}>"
    return value


def _safe_json(value: Any, limit: int = 1000) -> str:
    redacted = _redact_value(value)
    rendered = json.dumps(
        redacted,
        ensure_ascii=False,
        default=lambda item: f"<{type(item).__name__}>",
    )
    if len(rendered) <= limit:
        return rendered
    return f"{rendered[:limit]}..."


def _safe_url(url: str, include_query: bool) -> str:
    """userinfo를 제거하고 선택적으로 마스킹된 query만 포함한 로그용 URL을 만듭니다."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        port = None
    netloc = f"{hostname}:{port}" if port is not None else hostname

    query = ""
    if include_query and parsed.query:
        query = urlencode(
            [
                (key, _REDACTED if _is_sensitive_key(key) else value)
                for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            ],
            doseq=True,
        )

    return urlunparse(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            parsed.params,
            query,
            "",
        )
    )


def safe_exception_message(exc: BaseException) -> str:
    """예외 문자열에 포함된 URL의 userinfo/query/fragment를 제거한다."""
    message = str(exc)
    words = message.split()
    sanitized_words = []

    for word in words:
        prefix = ""
        candidate = word

        while candidate and candidate[0] in "([<{\"'":
            prefix += candidate[0]
            candidate = candidate[1:]

        suffix = ""
        while candidate and candidate[-1] in ")]>},.;:\"'":
            suffix = candidate[-1] + suffix
            candidate = candidate[:-1]

        lower_candidate = candidate.lower()
        absolute_indexes = [
            index
            for marker in ("https://", "http://")
            if (index := lower_candidate.find(marker)) >= 0
        ]

        if absolute_indexes:
            url_index = min(absolute_indexes)
            candidate = candidate[:url_index] + _safe_url(
                candidate[url_index:],
                include_query=False,
            )
        elif "?" in candidate or "#" in candidate:
            path_index = candidate.find("/")

            if path_index < 0:
                sanitized_words.append(prefix + candidate + suffix)
                continue

            relative_candidate = candidate[path_index:]
            parsed_candidate = urlparse(relative_candidate)
            safe_relative = urlunparse(
                (
                    "",
                    "",
                    parsed_candidate.path,
                    parsed_candidate.params,
                    "",
                    "",
                )
            )
            candidate = candidate[:path_index] + safe_relative

        sanitized_words.append(prefix + candidate + suffix)

    return " ".join(sanitized_words)


def _validate_positive_number(value: Any, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, numbers.Real) or value <= 0:
        raise ValueError(f"{name} must be a positive number")


def _validate_retry_count(value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("retry_count must be a positive integer")


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlparse(url)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("base_url and absolute endpoints must be valid HTTP(S) URLs")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("base_url and absolute endpoints must use a valid port") from exc
    effective_port = port or (443 if parsed.scheme.lower() == "https" else 80)
    return parsed.scheme.lower(), parsed.hostname.rstrip(".").lower(), effective_port


class NCPBaseClient:
    """
    네이버 클라우드 플랫폼 RESTful API 공용 클라이언트

    모든 HTTP 메서드(GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS)를 지원하며,
    다양한 파라미터 타입(string, int, float, list, dict, array)을 처리할 수 있습니다.
    """

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        base_url: str,
        timeout: int = API_TIMEOUT,
        retry_count: int = API_RETRY_COUNT,
    ):
        """
        API 클라이언트를 초기화합니다.

        Args:
            access_key: NCP Access Key
            secret_key: NCP Secret Key
            base_url: API 기본 URL
            timeout: 요청 타임아웃 (초)
            retry_count: 최대 요청 횟수(1 이상)
        """
        _validate_positive_number(timeout, "timeout")
        _validate_retry_count(retry_count)
        base_parts = urlparse(base_url)
        _origin(base_url)
        if base_parts.query or base_parts.fragment:
            raise ValueError("base_url must not contain a query string or fragment")

        self.auth = NCPAuth(access_key, secret_key)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry_count = retry_count
        self.session = requests.Session()

    def _prepare_params(self, params: Optional[Union[Dict, List]]) -> str:
        """
        파라미터를 쿼리 스트링으로 변환합니다.

        - bool: true / false 문자열 변환
        - dict, list: JSON 문자열 변환
        - 이미 만들어진 key 예: vpcNoList.1, sortList.1.sortedBy 는 그대로 유지
        """
        if not params:
            return ""

        processed_params = {}

        # 최상위 params가 list인 경우는 거의 없지만, 지원하려면 JSON으로 전달
        if isinstance(params, list):
            return urlencode({"items": json.dumps(params, ensure_ascii=False)})

        if isinstance(params, dict):
            for key, value in params.items():
                if value is None:
                    continue

                if isinstance(value, bool):
                    processed_params[key] = str(value).lower()
                elif isinstance(value, (dict, list)):
                    processed_params[key] = json.dumps(value, ensure_ascii=False)
                else:
                    processed_params[key] = str(value)

            return urlencode(processed_params)
        return ""

    def _prepare_headers(
        self,
        method: str,
        uri: str,
        custom_headers: Optional[Dict[str, str]] = None,
        query_string: Optional[str] = None,
    ) -> Dict[str, str]:
        """
        요청 헤더를 생성합니다.

        기본 동작:
            - Accept: application/json
            - POST/PUT/PATCH 인 경우 Content-Type: application/json 자동 추가
            - 인증 헤더 자동 추가
            - custom_headers 로 API별 헤더 override 가능

        예시:
            headers={
                'Accept': 'image/png'
            }

            headers={
                'Content-Type': 'application/xml'
            }

            headers={
                'Content-Type': 'multipart/form-data'
            }
        """

        headers = {"Accept": "application/json"}
        # 기본 JSON 요청 헤더
        if method.upper() in ["POST", "PUT", "PATCH"]:
            headers["Content-Type"] = "application/json"
        # 인증 헤더 생성
        auth_headers = self.auth.get_auth_headers(
            method,
            uri,
            query_string=query_string,
        )
        headers.update(auth_headers)
        # API별 커스텀 헤더 override
        # 동일 key 존재 시 덮어씀
        if custom_headers:
            headers.update(custom_headers)

        return headers

    def _resolve_request_url(self, endpoint: str) -> str:
        """인증정보를 보낼 수 있는 동일 origin의 요청 URL을 만든다."""
        endpoint_parts = urlparse(endpoint)
        is_absolute = bool(endpoint_parts.scheme or endpoint_parts.netloc)
        if is_absolute:
            if not endpoint_parts.scheme or not endpoint_parts.netloc:
                raise ValueError("absolute endpoint must include scheme and host")
            # NCP 인증 헤더가 외부 호스트로 전달되지 않도록 origin을 고정한다.
            if _origin(endpoint) != _origin(self.base_url):
                raise ValueError("absolute endpoint origin must match the configured base_url")
            return endpoint
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _merge_query_and_signature_uri(
        self,
        url: str,
        params: Optional[Union[Dict, List]],
    ) -> tuple[str, str]:
        """전송 URL과 정확히 같은 query를 포함한 서명 URI를 반환한다."""
        query_string = self._prepare_params(params)
        parsed_url = urlparse(url)
        merged_query = "&".join(part for part in (parsed_url.query, query_string) if part)
        parsed_url = parsed_url._replace(query=merged_query, fragment="")
        request_url = urlunparse(parsed_url)
        signature_uri = parsed_url.path
        if merged_query:
            signature_uri = f"{signature_uri}?{merged_query}"
        return request_url, signature_uri

    @staticmethod
    def _validate_body_modes(
        data: Optional[Union[Dict, List, str, bytes]],
        json_data: Optional[Union[Dict, List]],
        files: Optional[Dict],
    ) -> bool:
        has_files = bool(files)
        if json_data is not None and (data is not None or has_files):
            raise ValueError("json_data cannot be combined with data or files")
        if has_files and data is not None and not isinstance(data, dict):
            raise ValueError("files can only be combined with dict form data")
        return has_files

    def _build_request_kwargs(
        self,
        request_headers: Dict[str, str],
        *,
        data: Optional[Union[Dict, List, str, bytes]],
        json_data: Optional[Union[Dict, List]],
        files: Optional[Dict],
        timeout: Optional[int],
        has_files: bool,
    ) -> dict[str, Any]:
        request_timeout = timeout if timeout is not None else self.timeout
        _validate_positive_number(request_timeout, "timeout")
        request_kwargs: dict[str, Any] = {
            "headers": request_headers,
            "timeout": request_timeout,
            # NCP 인증 헤더가 Location의 다른 origin으로 전달되지 않도록
            # requests의 자동 redirect를 항상 금지한다.
            "allow_redirects": False,
        }

        if json_data is not None:
            request_kwargs["json"] = json_data
            return request_kwargs

        if has_files:
            # multipart boundary는 requests가 생성하므로 기본 Content-Type을 제거한다.
            for header_name in list(request_headers):
                if header_name.lower() == "content-type":
                    del request_headers[header_name]
            request_kwargs["files"] = files
            if data is not None:
                request_kwargs["data"] = data
            return request_kwargs

        if data is None:
            return request_kwargs

        content_type = next(
            (
                value.lower()
                for key, value in request_headers.items()
                if key.lower() == "content-type"
            ),
            "",
        )
        sends_raw_data = (
            "application/x-www-form-urlencoded" in content_type
            or "application/octet-stream" in content_type
            or "application/xml" in content_type
            or "text/xml" in content_type
            or content_type.startswith("text/")
        )
        if sends_raw_data or not isinstance(data, (dict, list)):
            request_kwargs["data"] = data
        else:
            request_kwargs["json"] = data
        return request_kwargs

    @staticmethod
    def _log_request(
        method: str,
        url: str,
        request_headers: Dict[str, str],
        *,
        params: Optional[Union[Dict, List]],
        data: Optional[Union[Dict, List, str, bytes]],
        json_data: Optional[Union[Dict, List]],
        files: Optional[Dict],
        has_files: bool,
    ) -> None:
        logger.info(
            "[API Request] %s %s",
            method,
            _safe_url(url, include_query=False),
        )
        logger.debug("  - URL: %s", _safe_url(url, include_query=True))
        logger.debug("  - Headers: %s", _safe_json(request_headers))

        if json_data is not None:
            logger.debug("  - Request Body (JSON): %s", _safe_json(json_data))
        elif data is not None:
            logger.debug("  - Request Body (Data): %s", _safe_json(data))

        if has_files:
            logger.debug(
                "  - Request File Fields: %s",
                [_REDACTED if _is_sensitive_key(key) else key for key in files],
            )

        if params:
            logger.debug("  - Query Params: %s", _safe_json(params))

    def _send_with_retry(
        self,
        method: str,
        url: str,
        request_kwargs: dict[str, Any],
        *,
        retry_safe: bool,
    ) -> requests.Response:
        # 읽기 전용 POST처럼 호출자가 멱등성을 보장한 경우에만 retry-safe를 쓴다.
        can_retry = method in _RETRYABLE_METHODS or retry_safe
        max_attempts = self.retry_count if can_retry else 1
        last_exception: Optional[requests.RequestException] = None

        for attempt in range(max_attempts):
            try:
                response = self.session.request(method, url, **request_kwargs)
                if response.status_code in _REDIRECT_STATUS_CODES:
                    raise requests.HTTPError(
                        "redirect responses are not allowed",
                        response=response,
                    )
                response.raise_for_status()
                return response
            except requests.RequestException as exc:
                last_exception = exc
                status_code = exc.response.status_code if exc.response is not None else None
                is_transient_http_error = status_code == 429 or (
                    status_code is not None and 500 <= status_code <= 599
                )
                is_connection_error = isinstance(
                    exc,
                    (requests.ConnectionError, requests.Timeout),
                )
                should_retry = (
                    can_retry
                    and (is_transient_http_error or is_connection_error)
                    and attempt < max_attempts - 1
                )

                if should_retry:
                    wait_time = 2**attempt
                    logger.warning(
                        "Transient request failure (method=%s, status=%s, attempt=%s/%s)",
                        method,
                        status_code if status_code is not None else type(exc).__name__,
                        attempt + 1,
                        max_attempts,
                    )
                    logger.info("Retrying in %s seconds...", wait_time)
                    time.sleep(wait_time)
                else:
                    logger.error(
                        "Request failed (method=%s, status=%s, attempts=%s)",
                        method,
                        status_code if status_code is not None else type(exc).__name__,
                        attempt + 1,
                    )
                    raise

        # retry_count는 생성 시 1 이상으로 검증되므로 방어적 경로이다.
        if last_exception is None:
            raise RuntimeError("request failed before an attempt was made")
        raise last_exception

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Union[Dict, List]] = None,
        data: Optional[Union[Dict, List, str, bytes]] = None,
        json_data: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        files: Optional[Dict] = None,
        timeout: Optional[int] = None,
        retry_safe: bool = False,
    ) -> requests.Response:
        """
        HTTP 요청을 실행합니다.

        동일한 base origin의 상대/절대 URL만 허용합니다. ``json_data``는
        ``data``/``files``와 함께 사용할 수 없으며, multipart 요청에서는
        ``files``와 form field용 dict ``data`` 조합만 허용합니다.
        """

        method = method.upper()
        url = self._resolve_request_url(endpoint)
        has_files = self._validate_body_modes(data, json_data, files)
        url, signature_uri = self._merge_query_and_signature_uri(url, params)
        request_headers = self._prepare_headers(
            method,
            signature_uri,
            custom_headers=headers,
            query_string=None,
        )
        request_kwargs = self._build_request_kwargs(
            request_headers,
            data=data,
            json_data=json_data,
            files=files,
            timeout=timeout,
            has_files=has_files,
        )
        self._log_request(
            method,
            url,
            request_headers,
            params=params,
            data=data,
            json_data=json_data,
            files=files,
            has_files=has_files,
        )
        return self._send_with_retry(
            method,
            url,
            request_kwargs,
            retry_safe=retry_safe,
        )

    @staticmethod
    def _log_response(response: requests.Response) -> None:
        logger.info("[API Response] Status: %s", response.status_code)
        logger.debug(
            "  - Response Headers: %s",
            _safe_json(dict(response.headers)),
        )
        logger.debug(
            "  - Response URL: %s",
            _safe_url(response.url or "", include_query=True),
        )

    @staticmethod
    def _decode_response(response: requests.Response) -> Any:
        if not response.text.strip():
            logger.info("  - Empty response body")
            return {
                "status_code": response.status_code,
                "empty": True,
            }

        content_type = response.headers.get("Content-Type", "").lower()
        is_json = "application/json" in content_type or "+json" in content_type
        is_xml = (
            "application/xml" in content_type
            or "text/xml" in content_type
            or "+xml" in content_type
        )
        is_text = content_type.startswith("text/") and not is_xml

        if is_text or is_xml:
            logger.info("  - Response Type: %s", "XML" if is_xml else "Text")
            logger.debug(
                "  - Response Body: <text length=%s>",
                len(response.text),
            )
            return {
                "text": response.text,
                "status_code": response.status_code,
            }

        if is_json:
            json_response = response.json()
        else:
            # Content-Type이 없거나 일반 바이너리인 기존 API와 호환하기 위해
            # JSON을 먼저 시도하고 실패하면 텍스트 envelope를 반환한다.
            try:
                json_response = response.json()
            except requests.exceptions.JSONDecodeError:
                logger.info("  - Response Type: Text")
                logger.debug(
                    "  - Response Body: <text length=%s>",
                    len(response.text),
                )
                return {
                    "text": response.text,
                    "status_code": response.status_code,
                }

        if isinstance(json_response, list):
            logger.info("  - Response Type: List (length: %s)", len(json_response))
        elif isinstance(json_response, dict):
            logger.info("  - Response Type: Dict")
            logger.info("  - Response Keys: %s", list(json_response.keys()))
        else:
            logger.info("  - Response Type: %s", type(json_response).__name__)
        logger.debug("  - Response Body: %s", _safe_json(json_response))
        return json_response

    def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Union[Dict, List]] = None,
        data: Optional[Union[Dict, List, str, bytes]] = None,
        json_data: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        files: Optional[Dict] = None,
        timeout: Optional[int] = None,
        retry_safe: bool = False,
    ) -> Any:
        """
        API 요청을 실행하고 응답을 반환합니다.

        모든 HTTP 메서드를 지원하며, 다양한 파라미터 타입을 처리할 수 있습니다.

        Args:
            method: HTTP 메서드 (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS)
            endpoint: API 엔드포인트 경로
            params: 쿼리 파라미터 (dict, list 지원)
            data: 요청 본문 데이터 (form 데이터, 문자열, 바이트)
            json_data: JSON 요청 본문 데이터 (dict, list 지원)
            headers: 커스텀 헤더
            files: 파일 업로드용 파일 딕셔너리
            timeout: 요청 타임아웃 (초)
            retry_safe: 읽기 전용 POST처럼 안전한 요청의 재시도 허용 여부

        Returns:
            Any: JSON은 디코딩된 값(dict/list/scalar), XML·텍스트는
            ``{"text": ..., "status_code": ...}``, 빈 본문은
            ``{"status_code": ..., "empty": True}``

        Raises:
            requests.RequestException: 요청 실패 시
            requests.exceptions.JSONDecodeError: JSON Content-Type 응답의
                JSON 파싱 실패 시

        Examples:
            # GET 요청
            response = client.request('GET', '/vserver/v2/getServerInstanceList')

            # POST 요청 (JSON)
            response = client.request('POST', '/vserver/v2/createServerInstances',
                                    json_data={'serverName': 'test'})

            # PUT 요청 (파라미터)
            response = client.request('PUT', '/vserver/v2/changeServerInstanceSpec',
                                    params={'serverInstanceNo': '123'})

            # PATCH 요청 (커스텀 헤더)
            response = client.request('PATCH', '/vserver/v2/updateServer',
                                    json_data={'name': 'new_name'},
                                    headers={'X-Custom-Header': 'value'})
        """
        response = self._make_request(
            method=method,
            endpoint=endpoint,
            params=params,
            data=data,
            json_data=json_data,
            headers=headers,
            files=files,
            timeout=timeout,
            retry_safe=retry_safe,
        )
        self._log_response(response)
        return self._decode_response(response)

    # 편의 메서드들
    def get(
        self,
        endpoint: str,
        params: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> Any:
        """GET 요청을 실행합니다."""
        return self.request(
            "GET",
            endpoint,
            params=params,
            headers=headers,
            timeout=timeout,
        )

    def get_binary(
        self,
        endpoint: str,
        params: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> bytes:
        """GET 요청을 실행하고 바이너리 응답을 반환합니다."""

        response = self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params,
            headers=headers,
            timeout=timeout,
        )

        logger.info(f"[Binary Response] Status: {response.status_code}")
        logger.info(f"  - Content-Type: {response.headers.get('Content-Type')}")
        logger.info(f"  - Content-Length: {response.headers.get('Content-Length')}")

        return response.content

    def post(
        self,
        endpoint: str,
        json_data: Optional[Union[Dict, List]] = None,
        data: Optional[Union[Dict, List, str, bytes]] = None,
        params: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        files: Optional[Dict] = None,
        timeout: Optional[int] = None,
        retry_safe: bool = False,
    ) -> Any:
        """POST 요청을 실행합니다."""
        return self.request(
            "POST",
            endpoint,
            json_data=json_data,
            data=data,
            params=params,
            headers=headers,
            files=files,
            timeout=timeout,
            retry_safe=retry_safe,
        )

    def put(
        self,
        endpoint: str,
        json_data: Optional[Union[Dict, List]] = None,
        data: Optional[Union[Dict, List, str, bytes]] = None,
        params: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> Any:
        """PUT 요청을 실행합니다."""
        return self.request(
            "PUT",
            endpoint,
            json_data=json_data,
            data=data,
            params=params,
            headers=headers,
            timeout=timeout,
        )

    def patch(
        self,
        endpoint: str,
        json_data: Optional[Union[Dict, List]] = None,
        data: Optional[Union[Dict, List, str, bytes]] = None,
        params: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> Any:
        """PATCH 요청을 실행합니다."""
        return self.request(
            "PATCH",
            endpoint,
            json_data=json_data,
            data=data,
            params=params,
            headers=headers,
            timeout=timeout,
        )

    def delete(
        self,
        endpoint: str,
        params: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> Any:
        """DELETE 요청을 실행합니다."""
        return self.request(
            "DELETE",
            endpoint,
            params=params,
            headers=headers,
            timeout=timeout,
        )

    def head(
        self,
        endpoint: str,
        params: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> requests.Response:
        """HEAD 요청을 실행합니다."""
        return self._make_request(
            "HEAD",
            endpoint,
            params=params,
            headers=headers,
            timeout=timeout,
        )

    def options(
        self,
        endpoint: str,
        params: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
    ) -> requests.Response:
        """OPTIONS 요청을 실행합니다."""
        return self._make_request(
            "OPTIONS",
            endpoint,
            params=params,
            headers=headers,
            timeout=timeout,
        )
