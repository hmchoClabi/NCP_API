"""고객 로고를 안전하게 검증하고 독립형 보고서에 삽입한다."""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Callable


MAX_CUSTOMER_LOGO_BYTES = 512 * 1024
MAX_CUSTOMER_LOGO_DIMENSION = 4096
MAX_CUSTOMER_LOGO_PIXELS = 8_000_000

_DATA_URI_PATTERN = re.compile(
    r"\Adata:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/]*={0,2})\Z"
)
_MAX_ENCODED_LOGO_LENGTH = 4 * ((MAX_CUSTOMER_LOGO_BYTES + 2) // 3)
_CONTENT_TYPE_ALIASES = {
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
}


@dataclass(frozen=True, slots=True)
class CustomerLogo:
    """검증을 통과한 고객 로고와 보고서 표시 메타데이터."""

    content: bytes
    content_type: str
    width: int
    height: int
    sha256: str

    @property
    def data_uri(self) -> str:
        encoded = base64.b64encode(self.content).decode("ascii")
        return f"data:{self.content_type};base64,{encoded}"


def validate_customer_logo(
    content: bytes,
    declared_content_type: str | None = None,
) -> CustomerLogo:
    """파일명이 아닌 실제 바이트를 기준으로 허용 형식과 크기를 검증한다.

    SVG는 이미지 태그에서도 브라우저별 active content 처리 차이가 있고 향후
    다른 렌더링 문맥에 재사용될 때 XSS 경계가 약해질 수 있어 허용하지 않는다.
    """
    if not isinstance(content, bytes):
        raise ValueError("로고 파일을 읽을 수 없습니다.")
    if not content:
        raise ValueError("비어 있는 로고 파일은 등록할 수 없습니다.")
    if len(content) > MAX_CUSTOMER_LOGO_BYTES:
        raise ValueError("고객사 로고는 512KB 이하여야 합니다.")

    detected = _detect_image(content)
    if detected is None:
        raise ValueError("PNG, JPEG 또는 WebP 로고만 등록할 수 있습니다.")
    content_type, width, height = detected

    declared = _normalize_declared_content_type(declared_content_type)
    if declared and declared != content_type:
        raise ValueError("파일 내용과 브라우저가 전달한 이미지 형식이 일치하지 않습니다.")
    if (
        width > MAX_CUSTOMER_LOGO_DIMENSION
        or height > MAX_CUSTOMER_LOGO_DIMENSION
        or width * height > MAX_CUSTOMER_LOGO_PIXELS
    ):
        raise ValueError(
            "고객사 로고는 가로·세로 4,096px 이하, 총 800만 픽셀 이하여야 합니다."
        )

    return CustomerLogo(
        content=content,
        content_type=content_type,
        width=width,
        height=height,
        sha256=sha256(content).hexdigest(),
    )


def normalize_customer_logo_data_uri(value: object) -> str | None:
    """스냅샷 로고를 다시 검증해 안전한 정규 data URI만 반환한다."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("고객사 로고 데이터가 올바르지 않습니다.")
    match = _DATA_URI_PATTERN.fullmatch(value.strip())
    if not match:
        raise ValueError("고객사 로고 data URI가 올바르지 않습니다.")
    if len(match.group(2)) > _MAX_ENCODED_LOGO_LENGTH:
        raise ValueError("고객사 로고는 512KB 이하여야 합니다.")
    try:
        content = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("고객사 로고의 Base64 데이터가 올바르지 않습니다.") from exc
    return validate_customer_logo(content, match.group(1)).data_uri


def _normalize_declared_content_type(value: str | None) -> str | None:
    normalized = str(value or "").partition(";")[0].strip().casefold()
    if not normalized or normalized == "application/octet-stream":
        return None
    return _CONTENT_TYPE_ALIASES.get(normalized, normalized)


def _detect_image(content: bytes) -> tuple[str, int, int] | None:
    detectors: tuple[
        tuple[str, Callable[[bytes], tuple[int, int] | None]], ...
    ] = (
        ("image/png", _png_dimensions),
        ("image/jpeg", _jpeg_dimensions),
        ("image/webp", _webp_dimensions),
    )
    for content_type, detector in detectors:
        dimensions = detector(content)
        if dimensions is not None:
            return content_type, *dimensions
    return None


def _png_dimensions(content: bytes) -> tuple[int, int] | None:
    if (
        len(content) < 33
        or content[:8] != b"\x89PNG\r\n\x1a\n"
        or content[12:16] != b"IHDR"
        or int.from_bytes(content[8:12], "big") != 13
    ):
        return None
    width = int.from_bytes(content[16:20], "big")
    height = int.from_bytes(content[20:24], "big")
    return (width, height) if width and height else None


def _jpeg_dimensions(content: bytes) -> tuple[int, int] | None:
    if len(content) < 4 or content[:2] != b"\xff\xd8":
        return None
    position = 2
    start_of_frame_markers = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    while position < len(content):
        if content[position] != 0xFF:
            return None
        while position < len(content) and content[position] == 0xFF:
            position += 1
        if position >= len(content):
            return None
        marker = content[position]
        position += 1
        if marker in {0x01, *range(0xD0, 0xD9)}:
            continue
        if marker in {0xD9, 0xDA} or position + 2 > len(content):
            return None
        segment_length = int.from_bytes(content[position:position + 2], "big")
        if segment_length < 2 or position + segment_length > len(content):
            return None
        if marker in start_of_frame_markers:
            if segment_length < 7:
                return None
            height = int.from_bytes(content[position + 3:position + 5], "big")
            width = int.from_bytes(content[position + 5:position + 7], "big")
            return (width, height) if width and height else None
        position += segment_length
    return None


def _webp_dimensions(content: bytes) -> tuple[int, int] | None:
    if (
        len(content) < 30
        or content[:4] != b"RIFF"
        or content[8:12] != b"WEBP"
        or int.from_bytes(content[4:8], "little") + 8 != len(content)
    ):
        return None
    chunk_type = content[12:16]
    if chunk_type == b"VP8X":
        width = int.from_bytes(content[24:27], "little") + 1
        height = int.from_bytes(content[27:30], "little") + 1
    elif chunk_type == b"VP8L" and content[20] == 0x2F:
        dimensions = int.from_bytes(content[21:25], "little")
        width = (dimensions & 0x3FFF) + 1
        height = ((dimensions >> 14) & 0x3FFF) + 1
    elif chunk_type == b"VP8 " and content[23:26] == b"\x9d\x01\x2a":
        width = int.from_bytes(content[26:28], "little") & 0x3FFF
        height = int.from_bytes(content[28:30], "little") & 0x3FFF
    else:
        return None
    return (width, height) if width and height else None
