"""
NCP 보고서 생성 프로그램
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence


from app.runner import ReportRunner

from config.settings import (
    NCP_ACCESS_KEY,
    NCP_SECRET_KEY,
    LOG_LEVEL,
    LOG_FILE,
)

LEGACY_DEFAULT_TARGET_MONTH = "2026-06"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NCP 사용량·이벤트·청구 보고서를 생성합니다.",
    )
    period_group = parser.add_mutually_exclusive_group()
    period_group.add_argument(
        "--target-month",
        metavar="YYYY-MM",
        help="지정한 월 전체를 조회합니다.",
    )
    period_group.add_argument(
        "--target-day",
        metavar="YYYY-MM-DD",
        help="지정한 하루를 조회합니다.",
    )
    period_group.add_argument(
        "--start-date",
        metavar="YYYY-MM-DD",
        help="기간 조회 시작일입니다. --end-date와 함께 사용합니다.",
    )
    parser.add_argument(
        "--end-date",
        metavar="YYYY-MM-DD",
        help="기간 조회 종료일입니다. --start-date와 함께 사용합니다.",
    )
    parser.add_argument(
        "--output-dir",
        help="보고서 저장 경로입니다. 생략하면 REPORT_OUTPUT_DIR를 사용합니다.",
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


def validate_settings() -> None:
    missing = [
        name
        for name, value in (
            ("NCP_ACCESS_KEY", NCP_ACCESS_KEY),
            ("NCP_SECRET_KEY", NCP_SECRET_KEY),
        )
        if not value
    ]

    if missing:
        logging.getLogger(__name__).error(
            "필수 환경 변수가 설정되지 않았습니다: %s",
            ", ".join(missing),
        )
        raise SystemExit(1)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if bool(args.start_date) != bool(args.end_date):
        parser.error("--start-date와 --end-date는 함께 지정해야 합니다.")

    setup_logging()
    validate_settings()

    target_month = args.target_month
    if not any(
        (
            target_month,
            args.target_day,
            args.start_date,
            args.end_date,
        )
    ):
        target_month = LEGACY_DEFAULT_TARGET_MONTH

    runner = ReportRunner(output_dir=args.output_dir)
    try:
        runner.get_period(
            target_month=target_month,
            target_day=args.target_day,
            start_date=args.start_date,
            end_date=args.end_date,
        )
    except ValueError as exc:
        parser.error(str(exc))

    runner.run(
        target_month=target_month,
        target_day=args.target_day,
        start_date=args.start_date,
        end_date=args.end_date,
    )


if __name__ == "__main__":
    main()
