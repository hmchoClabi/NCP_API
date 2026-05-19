"""
네이버 클라우드 플랫폼 월간 리포트 생성 프로그램

메인 실행 파일입니다.
"""

import sys
import logging
from datetime import datetime
from typing import Optional

from config.settings import (
    NCP_ACCESS_KEY, NCP_SECRET_KEY, NCP_REGION,
    API_ENDPOINTS, REPORT_OUTPUT_DIR, LOG_LEVEL, LOG_FILE, NCP_API_TYPE
)


from utils.common_rest import NCPBaseClient
from ncp_api import CloudInsightAPI, CloudActivityTracerAPI, SecurityMonitoringAPI, CertificateMgrAPI
from utils.data_utils import get_unix_time_stamp

# 로깅 설정
def setup_logging():
    """로깅을 설정합니다."""
    import os
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )


def main(
    year: Optional[int] = None,
    month: Optional[int] = None,
    range_type: str = 'previous_month',
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    interval_minutes: int = 15
):
    """
    메인 함수
    
    Args:
        year: 리포트를 생성할 년도 (None이면 현재 년도)
        month: 리포트를 생성할 월 (None이면 현재 월)
    """
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("네이버 클라우드 플랫폼 월간 리포트 생성 프로그램 시작")
    logger.info("=" * 60)
    
    # 인증 정보 확인
    if not NCP_ACCESS_KEY or not NCP_SECRET_KEY:
        logger.error("NCP_ACCESS_KEY 또는 NCP_SECRET_KEY가 설정되지 않았습니다.")
        logger.error("환경 변수 또는 config/settings.py 파일에서 설정해주세요.")
        sys.exit(1)
    
    if (start_date and not end_date) or (end_date and not start_date):
        logger.error("커스텀 기간을 사용하려면 --start-date와 --end-date를 모두 지정해야 합니다.")
        sys.exit(1)
    


    api_client = NCPBaseClient(
        access_key=NCP_ACCESS_KEY,
        secret_key=NCP_SECRET_KEY,
        base_url=API_ENDPOINTS['certificatemanager']  # 일반 서비스용 base_url
    )

    mgmt_api = CertificateMgrAPI(api_client)
    # vpc_response = mgmt_api.get_resource_list(page=0, size=300)
    # print(vpc_response)
    #vpc_response = mgmt_api.get_dashboard_list() 
    #vpc_response = mgmt_api.get_dashboard_widget_list(dashboard_id='df_567435234753253376')

    
    #이미지 다운로드 구문
    # starttime = get_unix_time_stamp("2026-04-29 00:00:00")
    # endtime = get_unix_time_stamp("2026-04-30 00:00:00")
    #vpc_response = mgmt_api.get_dashboard_widget_image(dashboard_id='df_567435234753253376', widget_id='mem_usert__567435234753253376',start_time=starttime, end_time=endtime )
    # with open("cloud-insight-widget.png", "wb") as f:
        # f.write(vpc_response)
    
    vpc_response = mgmt_api.get_certificate_list()
    print(vpc_response)
    

if __name__ == '__main__':
    # import argparse
    
    # parser = argparse.ArgumentParser(description='네이버 클라우드 플랫폼 월간 리포트 생성 프로그램')
    # parser.add_argument('--year', type=int, help='리포트를 생성할 년도 (기본값: 현재 년도)')
    # parser.add_argument('--month', type=int, help='리포트를 생성할 월 (기본값: 현재 월)')
    # parser.add_argument('--range', dest='range_type', choices=['previous_day', 'previous_week', 'previous_month', 'custom'], default='previous_month', help='보고 기간 유형 선택')
    # parser.add_argument('--start-date', help='커스텀 기간 시작일 (YYYY-MM-DD)')
    # parser.add_argument('--end-date', help='커스텀 기간 종료일 (YYYY-MM-DD)')
    # parser.add_argument('--interval-minutes', type=int, default=15, help='Cloud Insight 조회 간격(분)')
    
    # args = parser.parse_args()
    
    main(
        # year=args.year,
        # month=args.month,
        # range_type=args.range_type,
        # start_date=args.start_date,
        # end_date=args.end_date,
        # interval_minutes=args.interval_minutes
    )

