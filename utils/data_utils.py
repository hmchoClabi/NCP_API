"""보고 기간 계산과 NCP API timestamp 변환을 제공하는 날짜 유틸리티."""

import calendar
from dataclasses import dataclass
from datetime import datetime
from typing import Tuple
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta


KST = ZoneInfo("Asia/Seoul")


def _now_kst_naive() -> datetime:
    """기존 naive 반환 계약을 유지하면서 날짜 기준은 KST로 통일한다."""
    return datetime.now(KST).replace(tzinfo=None)


@dataclass
class DateTimeAPI:
    """현재·이전 보고 기간을 함께 전달하는 공개 호환 모델."""

    label: str
    file_key: str
    current_start: datetime
    current_end: datetime
    previous_start: datetime
    previous_end: datetime


def get_current_month_range() -> Tuple[datetime, datetime]:
    """현재 달의 시작일과 마지막 시각을 반환한다."""
    today = _now_kst_naive()
    start_date = datetime(today.year, today.month, 1)
    last_day = calendar.monthrange(today.year, today.month)[1]
    end_date = datetime(today.year, today.month, last_day, 23, 59, 59)
    return start_date, end_date


def get_previous_month_range() -> Tuple[datetime, datetime]:
    """이전 달의 시작일과 마지막 시각을 반환한다."""
    previous_month = _now_kst_naive() - relativedelta(months=1)
    start_date = datetime(previous_month.year, previous_month.month, 1)
    last_day = calendar.monthrange(
        previous_month.year,
        previous_month.month,
    )[1]
    end_date = datetime(
        previous_month.year,
        previous_month.month,
        last_day,
        23,
        59,
        59,
    )
    return start_date, end_date


def get_month_range(year: int, month: int) -> Tuple[datetime, datetime]:
    """지정한 달의 시작일과 마지막 시각을 반환한다."""
    start_date = datetime(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = datetime(year, month, last_day, 23, 59, 59)
    return start_date, end_date


def format_date(date: datetime, format_str: str = "%Y-%m-%d") -> str:
    """날짜를 기존 공개 포맷 계약에 따라 문자열로 변환한다."""
    return date.strftime(format_str)


def parse_date(date_str: str, format_str: str = "%Y-%m-%d") -> datetime:
    """날짜 문자열을 지정한 포맷의 ``datetime``으로 변환한다."""
    return datetime.strptime(date_str, format_str)


def get_month_name(year: int, month: int) -> str:
    """연월을 ``YYYY년 MM월`` 형식으로 반환한다."""
    return f"{year}년 {month:02d}월"


def get_unix_time_stamp(
    date_str: str,
    format_str: str = "%Y-%m-%d %H:%M:%S",
) -> int:
    """KST 현지 시각 문자열을 epoch millisecond로 변환한다."""
    dt = datetime.strptime(date_str, format_str)
    dt = dt.replace(tzinfo=KST)
    return int(dt.timestamp() * 1000)
