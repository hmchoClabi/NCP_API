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
        load_dotenv(dotenv_path=env_path, override=True)
        break
else:
    load_dotenv(override=True)


# ============================================================
# 기본 인증 정보
# ============================================================

NCP_ACCESS_KEY = os.getenv("NCP_ACCESS_KEY", "")
NCP_SECRET_KEY = os.getenv("NCP_SECRET_KEY", "")

NCP_API_TYPE = os.getenv("NCP_API_TYPE", "public").lower()
NCP_REGION = os.getenv("NCP_REGION", "KR").upper()


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

API_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))
API_RETRY_COUNT = int(os.getenv("API_RETRY_COUNT", "3"))


# ============================================================
# 리포트 설정
# ============================================================

REPORT_OUTPUT_DIR = os.getenv(
    "REPORT_OUTPUT_DIR",
    "./reports"
)


# ============================================================
# 날짜 포맷
# ============================================================

DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"