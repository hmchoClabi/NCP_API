"""
날짜 유틸리티 모듈

날짜 관련 유틸리티 함수를 제공합니다.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Tuple
from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo
import calendar
 

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
    today = datetime.now()
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
    today = datetime.now()
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


# def build_reporting_period(
#     range_type: str = 'previous_month',
#     year: Optional[int] = None,
#     month: Optional[int] = None,
#     start_date_str: Optional[str] = None,
#     end_date_str: Optional[str] = None
# ) -> ReportingPeriod:
#     """
#     보고 기간 정보를 생성합니다.
#     """
#     range_type = (range_type or 'previous_month').lower()
    
#     if start_date_str and end_date_str:
#         current_start = parse_date(start_date_str).replace(hour=0, minute=0, second=0)
#         end_date = parse_date(end_date_str)
#         current_end = end_date.replace(hour=23, minute=59, second=59)
#         suffix = " (사용자 지정)" if range_type == 'custom' else ''
#         label = f"{current_start.strftime('%Y-%m-%d')} ~ {current_end.strftime('%Y-%m-%d')}{suffix}"
#     elif year is not None and month is not None:
#         current_start, current_end = get_month_range(year, month)
#         label = get_month_name(year, month)
#     elif range_type == 'previous_day':
#         yesterday = (datetime.now() - timedelta(days=1)).date()
#         current_start = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0)
#         current_end = datetime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59)
#         label = f"{yesterday.strftime('%Y-%m-%d')} (전일)"
#     elif range_type == 'previous_week':
#         today = datetime.now().date()
#         current_week_start = today - timedelta(days=today.weekday())
#         previous_week_start = current_week_start - timedelta(days=7)
#         previous_week_end = current_week_start - timedelta(days=1)
#         current_start = datetime(previous_week_start.year, previous_week_start.month, previous_week_start.day, 0, 0, 0)
#         current_end = datetime(previous_week_end.year, previous_week_end.month, previous_week_end.day, 23, 59, 59)
#         label = f"{previous_week_start.strftime('%Y-%m-%d')} ~ {previous_week_end.strftime('%Y-%m-%d')} (전주)"
#     elif range_type == 'custom':
#         raise ValueError("커스텀 기간을 사용하려면 --start-date와 --end-date를 모두 지정해야 합니다.")
#     else:
#         target = datetime.now() - relativedelta(months=1) if range_type == 'previous_month' else datetime.now()
#         current_start, current_end = get_month_range(target.year, target.month)
#         label = get_month_name(target.year, target.month)
    
#     period_delta = current_end - current_start
#     previous_end = current_start - timedelta(seconds=1)
#     previous_start = previous_end - period_delta
    
#     file_key = f"{current_start.strftime('%Y%m%d')}_{current_end.strftime('%Y%m%d')}"
    
#     return ReportingPeriod(
#         label=label,
#         file_key=file_key,
#         current_start=current_start,
#         current_end=current_end,
#         previous_start=previous_start,
#         previous_end=previous_end
#     )



def get_unix_time_stamp(
    date_str: str,
    format_str: str = "%Y-%m-%d %H:%M:%S"
) -> int:

    kst = ZoneInfo("Asia/Seoul")

    dt = datetime.strptime(date_str, format_str)
    dt = dt.replace(tzinfo=kst)

    return int(dt.timestamp() * 1000)