"""외부 HTTPS URL의 고객 로고를 SSRF 없이 내려받는다."""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import threading
import time
import zlib
from collections.abc import Callable, Iterable
from queue import Empty, SimpleQueue
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit

from app.report_branding import (
    MAX_CUSTOMER_LOGO_BYTES,
    CustomerLogo,
    validate_customer_logo,
)


CUSTOMER_LOGO_FETCH_TIMEOUT_SECONDS = 8.0
CUSTOMER_LOGO_CONNECT_TIMEOUT_SECONDS = 3.0
CUSTOMER_LOGO_DNS_TIMEOUT_SECONDS = 2.0
MAX_CUSTOMER_LOGO_REDIRECTS = 3
MAX_CUSTOMER_LOGO_URL_LENGTH = 2_048

_ALLOWED_CONTENT_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
_CONTENT_TYPE_ALIASES = {
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
}
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_RESPONSE_CHUNK_BYTES = 64 * 1024


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """검증한 IP로만 연결하면서 원래 호스트명으로 TLS를 검증한다."""

    def __init__(
        self,
        hostname: str,
        resolved_ip: str,
        port: int,
        timeout: float,
    ) -> None:
        context = ssl.create_default_context()
        super().__init__(hostname, port, timeout=timeout, context=context)
        self._resolved_ip = resolved_ip

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._resolved_ip, self.port),
            timeout=self.timeout,
            source_address=self.source_address,
        )
        try:
            self.sock = self._context.wrap_socket(
                raw_socket,
                server_hostname=self.host,
            )
        except BaseException:
            raw_socket.close()
            raise


def fetch_customer_logo_from_url(
    value: str,
    *,
    resolver: Callable[..., Iterable[tuple[object, ...]]] = socket.getaddrinfo,
    connection_factory: Callable[
        [str, str, int, float], _PinnedHTTPSConnection
    ] = _PinnedHTTPSConnection,
) -> CustomerLogo:
    """공인 HTTPS 대상에서 로고를 받아 기존 로고 검증 모델로 반환한다.

    DNS 응답의 모든 주소를 먼저 검사한 뒤 검증된 IP를 연결 대상에 고정한다.
    따라서 검사 후 연결 사이에 호스트명을 다시 해석하는 DNS 재바인딩 경로가 없다.
    리다이렉트 대상도 동일한 절차로 매번 다시 검사한다.
    """
    current_url = _normalize_logo_url(value)
    visited_urls: set[str] = set()
    deadline = time.monotonic() + CUSTOMER_LOGO_FETCH_TIMEOUT_SECONDS

    for redirect_count in range(MAX_CUSTOMER_LOGO_REDIRECTS + 1):
        if current_url in visited_urls:
            raise ValueError("고객사 로고 URL이 순환 리다이렉트됩니다.")
        visited_urls.add(current_url)

        parsed = urlsplit(current_url)
        hostname = parsed.hostname
        if hostname is None:  # _normalize_logo_url에서 이미 방어하지만 타입을 좁힌다.
            raise ValueError("고객사 로고 URL의 호스트가 올바르지 않습니다.")
        resolved_ips = _resolve_public_ips(hostname, resolver, deadline)
        response, connection = _request_from_pinned_ip(
            parsed,
            resolved_ips,
            deadline,
            connection_factory,
        )
        try:
            if response.status in _REDIRECT_STATUSES:
                if redirect_count >= MAX_CUSTOMER_LOGO_REDIRECTS:
                    raise ValueError("고객사 로고 URL의 리다이렉트가 너무 많습니다.")
                location = response.getheader("Location")
                if not location:
                    raise ValueError("고객사 로고 리다이렉트 대상이 없습니다.")
                current_url = _normalize_logo_url(urljoin(current_url, location))
                continue
            if response.status != 200:
                raise ValueError(
                    "고객사 로고 URL이 정상 이미지를 반환하지 않았습니다 "
                    f"(HTTP {response.status})."
                )

            content_type = _response_content_type(response)
            _validate_response_size(response)
            content = _read_limited_body(response, connection, deadline)
            logo = validate_customer_logo(content, content_type)
            _validate_complete_image_container(logo)
            return logo
        finally:
            response.close()
            connection.close()

    raise ValueError("고객사 로고 URL의 리다이렉트가 너무 많습니다.")


def _normalize_logo_url(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("고객사 로고 URL이 올바르지 않습니다.")
    url = value.strip()
    if not url or len(url) > MAX_CUSTOMER_LOGO_URL_LENGTH:
        raise ValueError("고객사 로고 URL은 2,048자 이하의 HTTPS URL이어야 합니다.")
    if any(ord(character) <= 0x20 or ord(character) == 0x7F for character in url):
        raise ValueError("고객사 로고 URL에 허용되지 않는 문자가 있습니다.")

    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("고객사 로고 URL의 호스트 또는 포트가 올바르지 않습니다.") from exc
    if parsed.scheme.casefold() != "https":
        raise ValueError("고객사 로고는 HTTPS URL에서만 가져올 수 있습니다.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("인증정보가 포함된 고객사 로고 URL은 사용할 수 없습니다.")
    if parsed.fragment:
        raise ValueError("고객사 로고 URL에는 fragment를 사용할 수 없습니다.")
    if port not in {None, 443}:
        raise ValueError("고객사 로고 URL은 HTTPS 기본 포트(443)만 사용할 수 있습니다.")
    if not parsed.hostname:
        raise ValueError("고객사 로고 URL의 호스트가 올바르지 않습니다.")

    hostname = parsed.hostname.rstrip(".")
    if not hostname or "%" in hostname:
        raise ValueError("고객사 로고 URL의 호스트가 올바르지 않습니다.")
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            ascii_hostname = hostname.encode("idna").decode("ascii").casefold()
        except UnicodeError as exc:
            raise ValueError("고객사 로고 URL의 호스트가 올바르지 않습니다.") from exc
    else:
        ascii_hostname = literal_ip.compressed

    netloc = f"[{ascii_hostname}]" if ":" in ascii_hostname else ascii_hostname
    path = parsed.path or "/"
    return urlunsplit(("https", netloc, path, parsed.query, ""))


def _resolve_public_ips(
    hostname: str,
    resolver: Callable[..., Iterable[tuple[object, ...]]],
    deadline: float,
) -> tuple[str, ...]:
    result_queue: SimpleQueue[tuple[bool, object]] = SimpleQueue()

    def resolve() -> None:
        try:
            addresses = tuple(
                resolver(
                    hostname,
                    443,
                    family=socket.AF_UNSPEC,
                    type=socket.SOCK_STREAM,
                    proto=socket.IPPROTO_TCP,
                )
            )
            result_queue.put((True, addresses))
        except Exception as exc:  # DNS 공급자 예외는 사용자 입력 오류로 정규화한다.
            result_queue.put((False, exc))

    resolver_thread = threading.Thread(
        target=resolve,
        name="customer-logo-dns",
        daemon=True,
    )
    resolver_thread.start()
    resolver_thread.join(
        min(CUSTOMER_LOGO_DNS_TIMEOUT_SECONDS, _remaining(deadline))
    )
    if resolver_thread.is_alive():
        raise ValueError("고객사 로고 URL의 DNS 확인 시간이 초과되었습니다.")
    try:
        succeeded, payload = result_queue.get_nowait()
    except Empty as exc:
        raise ValueError("고객사 로고 URL의 호스트를 확인할 수 없습니다.") from exc
    if not succeeded:
        raise ValueError("고객사 로고 URL의 호스트를 확인할 수 없습니다.") from (
            payload if isinstance(payload, Exception) else None
        )
    addresses = payload if isinstance(payload, tuple) else ()

    resolved: list[str] = []
    for address in addresses:
        try:
            candidate = str(address[4][0])
            ip = ipaddress.ip_address(candidate)
        except (IndexError, TypeError, ValueError) as exc:
            raise ValueError("고객사 로고 URL의 DNS 응답이 올바르지 않습니다.") from exc
        if not _is_public_ip(ip):
            raise ValueError(
                "내부망·루프백·링크 로컬 주소를 가리키는 로고 URL은 사용할 수 없습니다."
            )
        normalized = ip.compressed
        if normalized not in resolved:
            resolved.append(normalized)
    if not resolved:
        raise ValueError("고객사 로고 URL의 호스트를 확인할 수 없습니다.")
    return tuple(resolved)


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_global
        and not ip.is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_multicast
        and not ip.is_reserved
        and not ip.is_unspecified
    )


def _request_from_pinned_ip(
    parsed: SplitResult,
    resolved_ips: tuple[str, ...],
    deadline: float,
    connection_factory: Callable[
        [str, str, int, float], _PinnedHTTPSConnection
    ],
) -> tuple[http.client.HTTPResponse, _PinnedHTTPSConnection]:
    hostname = parsed.hostname
    if hostname is None:
        raise ValueError("고객사 로고 URL의 호스트가 올바르지 않습니다.")
    request_target = parsed.path or "/"
    if parsed.query:
        request_target = f"{request_target}?{parsed.query}"

    last_error: BaseException | None = None
    for resolved_ip in resolved_ips:
        connection: _PinnedHTTPSConnection | None = None
        try:
            timeout = min(CUSTOMER_LOGO_CONNECT_TIMEOUT_SECONDS, _remaining(deadline))
            connection = connection_factory(hostname, resolved_ip, 443, timeout)
            connection.request(
                "GET",
                request_target,
                headers={
                    "Accept": "image/png,image/jpeg,image/webp",
                    "Accept-Encoding": "identity",
                    "Cache-Control": "no-cache",
                    "User-Agent": "NCP-Report-Logo-Fetcher/1.0",
                },
            )
            response = connection.getresponse()
            return response, connection
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            last_error = exc
            if connection is not None:
                connection.close()
    raise ValueError("고객사 로고 URL에 안전하게 연결할 수 없습니다.") from last_error


def _response_content_type(response: http.client.HTTPResponse) -> str:
    raw_content_type = response.getheader("Content-Type", "")
    content_type = raw_content_type.partition(";")[0].strip().casefold()
    content_type = _CONTENT_TYPE_ALIASES.get(content_type, content_type)
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise ValueError("로고 URL은 PNG, JPEG 또는 WebP 이미지를 반환해야 합니다.")
    content_encoding = response.getheader("Content-Encoding", "").strip().casefold()
    if content_encoding not in {"", "identity"}:
        raise ValueError("압축 전송된 고객사 로고 응답은 사용할 수 없습니다.")
    return content_type


def _validate_response_size(response: http.client.HTTPResponse) -> None:
    raw_length = response.getheader("Content-Length")
    if raw_length is None:
        return
    try:
        content_length = int(raw_length, 10)
    except (TypeError, ValueError) as exc:
        raise ValueError("고객사 로고 응답의 크기 정보가 올바르지 않습니다.") from exc
    if content_length < 0 or content_length > MAX_CUSTOMER_LOGO_BYTES:
        raise ValueError("고객사 로고는 512KB 이하여야 합니다.")


def _read_limited_body(
    response: http.client.HTTPResponse,
    connection: _PinnedHTTPSConnection,
    deadline: float,
) -> bytes:
    chunks: list[bytes] = []
    received = 0
    while True:
        timeout = _remaining(deadline)
        if connection.sock is not None:
            connection.sock.settimeout(timeout)
        try:
            chunk = response.read(
                min(_RESPONSE_CHUNK_BYTES, MAX_CUSTOMER_LOGO_BYTES + 1 - received)
            )
        except (OSError, http.client.HTTPException) as exc:
            raise ValueError("고객사 로고 URL의 이미지 수신에 실패했습니다.") from exc
        if not chunk:
            break
        received += len(chunk)
        if received > MAX_CUSTOMER_LOGO_BYTES:
            raise ValueError("고객사 로고는 512KB 이하여야 합니다.")
        chunks.append(chunk)
    return b"".join(chunks)


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError("고객사 로고 URL 응답 시간이 초과되었습니다.")
    return remaining


def _validate_complete_image_container(logo: CustomerLogo) -> None:
    """잘린 파일을 이미지 헤더로 오인하지 않도록 컨테이너 전체를 검사한다."""
    validators = {
        "image/png": _validate_png_container,
        "image/jpeg": _validate_jpeg_container,
        "image/webp": _validate_webp_container,
    }
    if not validators[logo.content_type](logo.content):
        raise ValueError("고객사 로고 이미지가 손상되었거나 완전하게 디코딩되지 않습니다.")


def _validate_png_container(content: bytes) -> bool:
    if content[:8] != b"\x89PNG\r\n\x1a\n":
        return False
    offset = 8
    first_chunk = True
    has_image_data = False
    while offset + 12 <= len(content):
        chunk_length = int.from_bytes(content[offset:offset + 4], "big")
        chunk_type = content[offset + 4:offset + 8]
        chunk_end = offset + 12 + chunk_length
        if chunk_end > len(content):
            return False
        chunk_data = content[offset + 8:offset + 8 + chunk_length]
        expected_crc = int.from_bytes(
            content[offset + 8 + chunk_length:chunk_end], "big"
        )
        if zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF != expected_crc:
            return False
        if first_chunk and (chunk_type != b"IHDR" or chunk_length != 13):
            return False
        first_chunk = False
        if chunk_type == b"IDAT":
            has_image_data = True
        if chunk_type == b"IEND":
            return chunk_length == 0 and has_image_data and chunk_end == len(content)
        offset = chunk_end
    return False


def _validate_jpeg_container(content: bytes) -> bool:
    if len(content) < 8 or content[:2] != b"\xff\xd8" or content[-2:] != b"\xff\xd9":
        return False
    position = 2
    while position + 4 <= len(content):
        if content[position] != 0xFF:
            return False
        while position < len(content) and content[position] == 0xFF:
            position += 1
        if position >= len(content):
            return False
        marker = content[position]
        position += 1
        if marker == 0xDA:  # SOS 이후 엔트로피 데이터는 최종 EOI까지 이미지 디코더가 처리한다.
            if position + 2 > len(content) - 2:
                return False
            segment_length = int.from_bytes(content[position:position + 2], "big")
            return (
                segment_length >= 2
                and position + segment_length <= len(content) - 2
            )
        if marker in {0x01, *range(0xD0, 0xD9)}:
            continue
        if marker in {0xD8, 0xD9} or position + 2 > len(content):
            return False
        segment_length = int.from_bytes(content[position:position + 2], "big")
        if segment_length < 2 or position + segment_length > len(content) - 2:
            return False
        position += segment_length
    return False


def _validate_webp_container(content: bytes) -> bool:
    if (
        len(content) < 20
        or content[:4] != b"RIFF"
        or content[8:12] != b"WEBP"
        or int.from_bytes(content[4:8], "little") + 8 != len(content)
    ):
        return False
    offset = 12
    has_image_payload = False
    while offset + 8 <= len(content):
        chunk_type = content[offset:offset + 4]
        chunk_length = int.from_bytes(content[offset + 4:offset + 8], "little")
        chunk_end = offset + 8 + chunk_length
        padded_end = chunk_end + (chunk_length % 2)
        if chunk_end > len(content) or padded_end > len(content):
            return False
        if chunk_type in {b"VP8 ", b"VP8L", b"ANMF"}:
            has_image_payload = True
        offset = padded_end
    return offset == len(content) and has_image_payload
