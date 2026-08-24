"""웹 포털의 템플릿 표현 규칙을 등록한다."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from flask import Flask, g


KST = ZoneInfo("Asia/Seoul")


def format_kst(
    value: Any,
    format_string: str = "%Y-%m-%d %H:%M:%S",
) -> str:
    """템플릿 값을 한국 표준시 문자열로 표시한다."""
    if value is None:
        return "-"
    parsed = value
    if isinstance(parsed, str):
        try:
            parsed = datetime.fromisoformat(parsed)
        except ValueError:
            return parsed
    if not isinstance(parsed, datetime):
        return str(parsed)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return f"{parsed.astimezone(KST).strftime(format_string)} KST"


def format_duration(value: Any) -> str:
    """초 단위 값을 사람이 읽기 쉬운 한국어 기간으로 표시한다."""
    if value is None:
        return "-"
    try:
        total_seconds = max(int(value), 0)
    except (TypeError, ValueError, OverflowError):
        return str(value)
    days, remainder = divmod(total_seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}일")
    if hours:
        parts.append(f"{hours}시간")
    if minutes:
        parts.append(f"{minutes}분")
    if seconds or not parts:
        parts.append(f"{seconds}초")
    return " ".join(parts)


def inclusive_period_end(value: Any, end_exclusive: Any = True) -> Any:
    """배타적 종료 시각을 화면 표시용 포함 종료 시각으로 변환한다."""
    exclusive = (
        end_exclusive
        if isinstance(end_exclusive, bool)
        else _as_bool(end_exclusive, True)
        if isinstance(end_exclusive, str)
        else True
    )
    if value is None or not exclusive:
        return value
    parsed = value
    if isinstance(parsed, str):
        try:
            parsed = datetime.fromisoformat(parsed.replace("Z", "+00:00"))
        except ValueError:
            return value
    if not isinstance(parsed, datetime):
        return value
    return parsed - timedelta(microseconds=1)


def register_presentation(app: Flask) -> None:
    """템플릿 필터와 공통 문맥을 애플리케이션에 등록한다.

    라우트와 표현 변환의 경계를 분리하되 기존 필터 이름과 문맥 키는
    템플릿 호환 계약이므로 그대로 유지한다.
    """
    app.add_template_filter(format_kst, "kst")
    app.add_template_filter(format_duration, "duration")
    app.add_template_filter(inclusive_period_end, "inclusive_end")

    @app.context_processor
    def template_context() -> dict[str, Any]:
        now = datetime.now(KST)
        today = now.date()
        previous_month_end = today.replace(day=1) - timedelta(days=1)
        previous_week = today - timedelta(days=today.isoweekday())
        iso_year, iso_week, _ = previous_week.isocalendar()
        return {
            "current_user": g.get("user"),
            "csrf_token": g.get("csrf_token", ""),
            "default_daily_target": (today - timedelta(days=1)).isoformat(),
            "default_monthly_target": previous_month_end.strftime("%Y-%m"),
            "default_weekly_target": f"{iso_year:04d}-W{iso_week:02d}",
            "default_range_start": (
                now.replace(second=0, microsecond=0) - timedelta(hours=1)
            ).strftime("%Y-%m-%dT%H:%M"),
            "default_range_end": now.replace(
                second=0,
                microsecond=0,
            ).strftime("%Y-%m-%dT%H:%M"),
            "notification_since": datetime.now(timezone.utc).isoformat(),
            "app_version": str(app.config["APP_VERSION"]),
            "app_source_revision": str(app.config["APP_SOURCE_REVISION"]),
        }


def _as_bool(value: str | None, default: bool) -> bool:
    """기존 템플릿 필터의 느슨한 불리언 변환 계약을 유지한다."""
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}
