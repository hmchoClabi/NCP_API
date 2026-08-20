"""
NCP 보고서 생성 프로그램
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Sequence
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


from app.apifactory import APIFactory
from app.customer import CustomerProfile, customer_id_from_name
from app.mailers import SMTPConfig, SMTPMailer, parse_recipients
from app.renderers import HtmlReportRenderer
from app.report_models import ReportResult
from database import build_report_repository_from_env
from app.runner import ReportRunner

from config.settings import (
    NCP_ACCESS_KEY,
    NCP_API_TYPE,
    NCP_REGION,
    NCP_SECRET_KEY,
    LOG_LEVEL,
    LOG_FILE,
)
from utils.credential_provider import EnvironmentCredentialProvider
from utils.credentials import NCPCredentials

DAY_ALIASES = {
    "today": 0,
    "오늘": 0,
    "yesterday": -1,
    "어제": -1,
}

MONTH_ALIASES = {
    "this-month": 0,
    "this_month": 0,
    "이번달": 0,
    "이번 달": 0,
    "last-month": -1,
    "last_month": -1,
    "지난달": -1,
    "지난 달": -1,
}


def get_korea_timezone():
    """한국 시간대를 반환합니다."""
    try:
        return ZoneInfo("Asia/Seoul")
    except ZoneInfoNotFoundError:
        # Windows에 IANA timezone 데이터가 없을 경우 사용합니다.
        return timezone(timedelta(hours=9), name="KST")


KOREA_TIMEZONE = get_korea_timezone()


def resolve_target_day(
    value: Optional[str],
    *,
    reference_date: Optional[date] = None,
) -> Optional[str]:
    """
    날짜 또는 상대 날짜 표현을 YYYY-MM-DD 형식으로 변환합니다.

    지원 값:
    - YYYY-MM-DD
    - today, 오늘
    - yesterday, 어제
    """
    if value is None:
        return None

    normalized = value.strip().casefold()
    if not normalized:
        raise ValueError("--target-day 값이 비어 있습니다.")

    base_date = (
        reference_date
        or datetime.now(KOREA_TIMEZONE).date()
    )

    day_offset = DAY_ALIASES.get(normalized)

    if day_offset is not None:
        return (
            base_date + timedelta(days=day_offset)
        ).isoformat()

    try:
        return date.fromisoformat(normalized).isoformat()
    except ValueError as exc:
        raise ValueError(
            "--target-day는 YYYY-MM-DD, today, yesterday, "
            "오늘, 어제 중 하나여야 합니다."
        ) from exc


def shift_month(
    reference_date: date,
    month_offset: int,
) -> str:
    """기준 날짜에서 지정한 개월만큼 이동한 YYYY-MM을 반환합니다."""
    month_index = (
        reference_date.year * 12
        + reference_date.month
        - 1
        + month_offset
    )

    year, zero_based_month = divmod(month_index, 12)

    return f"{year:04d}-{zero_based_month + 1:02d}"


def resolve_target_month(
    value: Optional[str],
    *,
    reference_date: Optional[date] = None,
) -> Optional[str]:
    """
    월 또는 상대 월 표현을 YYYY-MM 형식으로 변환합니다.

    지원 값:
    - YYYY-MM
    - this-month, 이번달
    - last-month, 지난달
    """
    if value is None:
        return None

    normalized = value.strip().casefold()
    if not normalized:
        raise ValueError("--target-month 값이 비어 있습니다.")

    base_date = (
        reference_date
        or datetime.now(KOREA_TIMEZONE).date()
    )

    month_offset = MONTH_ALIASES.get(normalized)

    if month_offset is not None:
        return shift_month(
            reference_date=base_date,
            month_offset=month_offset,
        )

    try:
        parsed = date.fromisoformat(
            f"{normalized}-01"
        )
    except ValueError as exc:
        raise ValueError(
            "--target-month는 YYYY-MM, this-month, last-month, "
            "이번달, 지난달 중 하나여야 합니다."
        ) from exc

    return f"{parsed.year:04d}-{parsed.month:02d}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NCP 사용량·이벤트·청구 보고서를 생성합니다.",
    )
    period_group = parser.add_mutually_exclusive_group()
    period_group.add_argument(
        "--target-month",
        metavar="YYYY-MM|this-month|last-month",
         help=(
        "지정한 월 전체를 조회합니다. "
        "this-month/이번달, last-month/지난달도 사용할 수 있습니다."
        ),
    )
    period_group.add_argument(
        "--target-day",
         metavar="YYYY-MM-DD|today|yesterday",
        help=(
        "지정한 하루를 조회합니다. "
        "today/오늘, yesterday/어제도 사용할 수 있습니다."
        ),
    )
    period_group.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        help="기간 조회 시작일입니다. --end-date와 함께 사용합니다.",
    )
    period_group.add_argument(
        "--start-datetime",
        metavar="DATE HH:MM[:SS]",
        help=(
            "KST 기준 조회 시작 일시입니다. --end-datetime과 함께 사용하며 "
            "날짜에는 YYYY-MM-DD, today/오늘, yesterday/어제를 사용할 수 "
            "있고 ISO 8601 시간대도 지원합니다."
        ),
    )
    parser.add_argument(
        "--end-date",
        metavar="YYYY-MM-DD",
        help="기간 조회 종료일입니다. --start-date와 함께 사용합니다.",
    )
    parser.add_argument(
        "--end-datetime",
        metavar="DATE HH:MM[:SS]",
        help=(
            "조회 종료 경계(미포함)입니다. 날짜에 today/오늘 또는 "
            "yesterday/어제를 사용할 수 있습니다."
        ),
    )
    parser.add_argument(
        "--output-dir",
        help="보고서 저장 경로입니다. 생략하면 REPORT_OUTPUT_DIR를 사용합니다.",
    )
    parser.add_argument(
        "--send-email",
        action="store_true",
        help="Send the generated HTML report by SMTP email.",
    )
    parser.add_argument(
        "--email-to",
        action="append",
        metavar="EMAIL[,EMAIL...]",
        help=(
            "Email recipients. Repeat the option or separate addresses with "
            "commas. Defaults to REPORT_EMAIL_TO."
        ),
    )
    parser.add_argument(
        "--customer-id",
        help=(
            "Stable customer identifier used for output isolation. Defaults "
            "to NCP_CUSTOMER_ID or a value derived from the customer name."
        ),
    )
    parser.add_argument(
        "--customer-name",
        help="Customer display name. Defaults to NCP_CUSTOMER_NAME.",
    )
    parser.add_argument(
        "--api-type",
        choices=("public", "gov"),
        help="NCP environment. Defaults to NCP_API_TYPE.",
    )
    parser.add_argument(
        "--region",
        help="NCP region code. Defaults to NCP_REGION.",
    )
    return parser



def setup_logging() -> None:
    log_path = Path(LOG_FILE).expanduser()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(
            logging,
            LOG_LEVEL.upper(),
            logging.INFO,
        ),
        format=(
            "%(asctime)s - "
            "%(name)s - "
            "%(levelname)s - "
            "%(message)s"
        ),
        handlers=[
            logging.FileHandler(
                log_path,
                encoding="utf-8",
            ),
            logging.StreamHandler(sys.stdout),
        ],
    )


def validate_settings(
    credentials: Optional[NCPCredentials] = None,
) -> None:
    credentials = credentials or NCPCredentials(
        access_key=NCP_ACCESS_KEY,
        secret_key=NCP_SECRET_KEY,
        api_type=NCP_API_TYPE,
        region=NCP_REGION,
        account_name="default",
    )
    missing = [
        name
        for name, value in (
            ("NCP_ACCESS_KEY", credentials.access_key),
            ("NCP_SECRET_KEY", credentials.secret_key),
        )
        if not value
    ]

    if missing:
        logging.getLogger(__name__).error(
            "필수 환경 변수가 설정되지 않았습니다: %s",
            ", ".join(missing),
        )
        raise SystemExit(1)


def build_customer_profile(args: argparse.Namespace) -> CustomerProfile:
    customer_name = (
        args.customer_name
        or os.getenv("NCP_CUSTOMER_NAME")
        or "default"
    ).strip()
    customer_id = (
        args.customer_id
        or os.getenv("NCP_CUSTOMER_ID")
        or (
            "default"
            if customer_name == "default"
            else customer_id_from_name(customer_name)
        )
    )
    return CustomerProfile(
        customer_id=customer_id,
        customer_name=customer_name,
        api_type=(
            args.api_type
            or os.getenv("NCP_API_TYPE")
            or NCP_API_TYPE
        ),
        region=(
            args.region
            or os.getenv("NCP_REGION")
            or NCP_REGION
        ),
        credential_ref=os.getenv("NCP_CREDENTIAL_REF") or None,
    )


def send_report_email(
    report: ReportResult,
    runner: ReportRunner,
    recipient_values: Optional[Sequence[str]] = None,
) -> str:
    recipients = parse_recipients(
        recipient_values
        if recipient_values
        else [os.getenv("REPORT_EMAIL_TO", "")]
    )
    if not recipients:
        raise ValueError(
            "--send-email requires --email-to or REPORT_EMAIL_TO."
        )

    period = report.period
    start_dt = str(period.get("start_dt", "")).split(" ", 1)[0]
    end_dt = str(period.get("end_dt", "")).split(" ", 1)[0]
    period_type = str(period.get("period_type", "report"))
    report_label = "월간" if period.get("is_full_month") else "일간"
    if period_type == "range":
        report_label = "기간"
    customer_name = str(report.customer.get("name") or "").strip()
    customer_prefix = f"{customer_name} " if customer_name else ""

    attachment = (
        Path(runner.output_dir)
        / f"ncp_report_{period['file_suffix']}.html"
    )
    subject = (
        f"[{customer_prefix}NCP {report_label} 보고서] "
        f"{start_dt} ~ {end_dt}"
    )
    body = (
        "NCP 보고서가 생성되었습니다.\n\n"
        f"고객명: {customer_name or '-'}\n"
        f"보고서 유형: {report_label}\n"
        f"조회 기간: {start_dt} ~ {end_dt}\n"
        f"생성 시각: {report.generated_at}\n\n"
        "첨부된 HTML 보고서를 확인해 주세요.\n"
    )

    message_id = SMTPMailer(SMTPConfig.from_env()).send(
        subject=subject,
        body=body,
        recipients=recipients,
        attachments=[attachment],
        html_body=HtmlReportRenderer().render_email_summary(report),
    )
    logging.getLogger(__name__).info(
        "보고서 메일 전송 완료: message_id=%s, recipients=%d",
        message_id,
        len(recipients),
    )
    return message_id


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if bool(args.start_date) != bool(args.end_date):
        parser.error(
            "--start-date와 --end-date는 함께 지정해야 합니다."
        )
    if bool(args.start_datetime) != bool(args.end_datetime):
        parser.error(
            "--start-datetime과 --end-datetime은 함께 지정해야 합니다."
        )

    try:
        target_month = resolve_target_month(
            args.target_month
        )
        target_day = resolve_target_day(
            args.target_day
        )
    except ValueError as exc:
        parser.error(str(exc))

    setup_logging()
    logger = logging.getLogger(__name__)

    if target_day and args.target_day != target_day:
        logger.info(
            "상대 날짜 변환: %s -> %s",
            args.target_day,
            target_day,
        )

    if target_month and args.target_month != target_month:
        logger.info(
            "상대 월 변환: %s -> %s",
            args.target_month,
            target_month,
        )

    customer = build_customer_profile(args)

    credential_provider = EnvironmentCredentialProvider()
    credentials = credential_provider.get_credentials(
        customer
    )
    validate_settings(credentials)

    api_factory = APIFactory(
        credentials=credentials
    )

    runner = ReportRunner(
        output_dir=args.output_dir,
        api_factory=api_factory,
        customer=customer,
        report_repository=build_report_repository_from_env(),
    )

    period_arguments = {
        "target_month": target_month,
        "target_day": target_day,
        "start_date": args.start_date,
        "end_date": args.end_date,
    }
    if args.start_datetime or args.end_datetime:
        period_arguments.update(
            start_datetime=args.start_datetime,
            end_datetime=args.end_datetime,
        )

    try:
        runner.get_period(**period_arguments)
    except ValueError as exc:
        parser.error(str(exc))

    report = runner.run(**period_arguments)

    if args.send_email:
        send_report_email(
            report=report,
            runner=runner,
            recipient_values=args.email_to,
        )


if __name__ == "__main__":
    main()
