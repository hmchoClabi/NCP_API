import os
from pathlib import Path

from dotenv import load_dotenv
from config.endpoints import build_api_endpoints


# ============================================================
# .env 로드
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

for env_path in [PROJECT_ROOT / ".env", Path.cwd() / ".env"]:
    if env_path.exists():
        # 프로세스 환경 변수가 배포 환경의 명시적 설정이므로 .env보다 우선합니다.
        load_dotenv(dotenv_path=env_path, override=False)
        break
else:
    load_dotenv(override=False)


def _read_positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}은 양의 정수여야 합니다: {raw_value!r}") from exc
    if value <= 0:
        raise ValueError(f"{name}은 양의 정수여야 합니다: {raw_value!r}")
    return value


# ============================================================
# 기본 인증 정보
# ============================================================

NCP_ACCESS_KEY = os.getenv("NCP_ACCESS_KEY", "")
NCP_SECRET_KEY = os.getenv("NCP_SECRET_KEY", "")

NCP_API_TYPE = os.getenv("NCP_API_TYPE", "public").strip().lower()
NCP_REGION = os.getenv("NCP_REGION", "KR").strip().upper()


# ============================================================
# Endpoint 생성
# ============================================================

API_ENDPOINTS = build_api_endpoints(
    api_type=NCP_API_TYPE,
    region=NCP_REGION,
)


# ============================================================
# 로깅 설정
# ============================================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "./logs/ncp_report.log")


# ============================================================
# API 설정
# ============================================================

API_TIMEOUT = _read_positive_int("API_TIMEOUT", 30)
API_RETRY_COUNT = _read_positive_int("API_RETRY_COUNT", 3)


# ============================================================
# 리포트 설정
# ============================================================

REPORT_OUTPUT_DIR = os.getenv(
    "REPORT_OUTPUT_DIR",
    "./reports"
)
