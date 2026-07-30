"""
날짜 유틸리티 모듈

날짜 관련 유틸리티 함수를 제공합니다.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Tuple
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo
import calendar


KST = ZoneInfo("Asia/Seoul")


def _now_kst_naive() -> datetime:
    """기존 naive 반환 계약을 유지하면서 날짜 기준은 KST로 통일합니다."""
    return datetime.now(KST).replace(tzinfo=None)

@dataclass
class DateTimeAPI:
    """
    리포트 기간 정보
    """
    label: str
    file_key: str
    current_start: datetime
    current_end: datetime
    previous_start: datetime
    previous_end: datetime


def get_current_month_range() -> Tuple[datetime, datetime]:
    """
    현재 달의 시작일과 종료일을 반환합니다.
    
    Returns:
        Tuple[datetime, datetime]: (시작일, 종료일) 튜플
    """
    today = _now_kst_naive()
    start_date = datetime(today.year, today.month, 1)
    
    # 다음 달 1일에서 1일을 빼서 현재 달의 마지막 날을 구함
    last_day = calendar.monthrange(today.year, today.month)[1]
    end_date = datetime(today.year, today.month, last_day, 23, 59, 59)
    
    return start_date, end_date


def get_previous_month_range() -> Tuple[datetime, datetime]:
    """
    이전 달의 시작일과 종료일을 반환합니다.
    
    Returns:
        Tuple[datetime, datetime]: (시작일, 종료일) 튜플
    """
    today = _now_kst_naive()
    prev_month = today - relativedelta(months=1)
    
    start_date = datetime(prev_month.year, prev_month.month, 1)
    last_day = calendar.monthrange(prev_month.year, prev_month.month)[1]
    end_date = datetime(prev_month.year, prev_month.month, last_day, 23, 59, 59)
    
    return start_date, end_date


def get_month_range(year: int, month: int) -> Tuple[datetime, datetime]:
    """
    지정된 년도와 월의 시작일과 종료일을 반환합니다.
    
    Args:
        year: 년도
        month: 월 (1-12)
    
    Returns:
        Tuple[datetime, datetime]: (시작일, 종료일) 튜플
    """
    start_date = datetime(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = datetime(year, month, last_day, 23, 59, 59)
    
    return start_date, end_date


def format_date(date: datetime, format_str: str = '%Y-%m-%d') -> str:
    """
    날짜를 지정된 형식의 문자열로 변환합니다.
    
    Args:
        date: 변환할 날짜
        format_str: 날짜 형식 문자열
    
    Returns:
        str: 포맷된 날짜 문자열
    """
    return date.strftime(format_str)


def parse_date(date_str: str, format_str: str = '%Y-%m-%d') -> datetime:
    """
    날짜 문자열을 datetime 객체로 변환합니다.
    
    Args:
        date_str: 날짜 문자열
        format_str: 날짜 형식 문자열
    
    Returns:
        datetime: 변환된 datetime 객체
    """
    return datetime.strptime(date_str, format_str)


def get_month_name(year: int, month: int) -> str:
    """
    년도와 월을 받아서 "YYYY년 MM월" 형식의 문자열을 반환합니다.
    
    Args:
        year: 년도
        month: 월 (1-12)
    
    Returns:
        str: "YYYY년 MM월" 형식의 문자열
    """
    return f"{year}년 {month:02d}월"


def get_unix_time_stamp(
    date_str: str,
    format_str: str = "%Y-%m-%d %H:%M:%S"
) -> int:

    dt = datetime.strptime(date_str, format_str)
    dt = dt.replace(tzinfo=KST)

    return int(dt.timestamp() * 1000)
