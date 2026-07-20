"""
NCP 보고서 생성 프로그램
"""

import logging
import os
import sys


from app.runner import ReportRunner

from config.settings import (
    NCP_ACCESS_KEY,
    NCP_SECRET_KEY,
    LOG_LEVEL,
    LOG_FILE,
)



def setup_logging():

    os.makedirs(
        os.path.dirname(LOG_FILE),
        exist_ok=True,
    )

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
                LOG_FILE,
                encoding="utf-8",
            ),
            logging.StreamHandler(sys.stdout),
        ],
    )


def validate_settings():

    logger = logging.getLogger(__name__)

    if not NCP_ACCESS_KEY:
        logger.error(
            "NCP_ACCESS_KEY가 설정되지 않았습니다."
        )
        sys.exit(1)

    if not NCP_SECRET_KEY:
        logger.error(
            "NCP_SECRET_KEY가 설정되지 않았습니다."
        )
        sys.exit(1)


def main():

    setup_logging()

    validate_settings()

    runner = ReportRunner()

    # 특정 월
    runner.run(target_month="2026-06")

    # 특정 하루
    # runner.run(target_day="2026-05-15")

    # # 특정 기간
    # runner.run( 
    #     start_date="2026-05-10",
    #     end_date="2026-05-20",
    # )


if __name__ == "__main__":
    main()