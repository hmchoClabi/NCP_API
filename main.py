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
    API_ENDPOINTS, REPORT_OUTPUT_DIR, LOG_LEVEL, LOG_FILE,
    CLOUD_INSIGHT_CW_KEY, NCP_API_TYPE
)


from utils.common_rest import NCPBaseClient
from ncp_api.vserverAPI import VServerAPI
from ncp_api.platformAPI import PlatformAPI
from ncp_api.containerAPI import ContainerAPI
from ncp_api.kubernetesAPI import KubernetesAPI
from ncp_api.vnasAPI import VNasAPI
from ncp_api.networkAPI import NetworkAPI
from ncp_api.resourcemgrAPI import ResourceManagerAPI


# from ncp_api.server import ServerAPI
# from ncp_api.monitoring import MonitoringAPI
# from ncp_api.storage import StorageAPI
# from ncp_api.network import NetworkAPI
# from ncp_api.kubernetes import KubernetesAPI
# from report.resource_summary import ResourceSummaryCollector
# from report.data_collector import DataCollector
# from report.data_analyzer import DataAnalyzer
# from report.report_generator import ReportGenerator
from utils.data_utils import build_reporting_period

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
    
    try:
        reporting_period = build_reporting_period(
            range_type=range_type,
            year=year,
            month=month,
            start_date_str=start_date,
            end_date_str=end_date
        )
    except ValueError as exc:
        logger.error(str(exc))
        sys.exit(1)

    api_client = NCPBaseClient(
        access_key=NCP_ACCESS_KEY,
        secret_key=NCP_SECRET_KEY,
        base_url=API_ENDPOINTS['resourcemanager']  # 일반 서비스용 base_url
    )

    mgmt_api = ResourceManagerAPI(api_client)
    # vpc_response = mgmt_api.get_resource_list(page=0, size=300)
    # print(vpc_response)
    vpc_response = mgmt_api.get_group_list()
    print(vpc_response)

#102557
    


    # registry_response = resource_api.get_registry_list()
    # print(registry_response)
    # logger.debug(f"지역 목록 응답 키: {list(registry_response.keys())}")

    # registry_response = resource_api.get_image_list(registry_id='rnd-nks-reg')
    # print(registry_response)
    # logger.debug(f"이미지 목록 응답 키: {list(registry_response.keys())}")

    
    

    # registry_response = kubernetes_api.get_nks_kubeconfig(uuid='12757453-d58e-4aa2-abd6-da36ee318628')
    # print(registry_response)
    
    #logger.debug(f"이미지 상세 정보 응답 키: {list(registry_response.keys())}")

    #server_list_response = resource_api.get_server_instance_list(region_code=NCP_REGION)
    #logger.debug(f"서버 목록 응답 키: {list(server_list_response.keys())}")

    
#     current_start = reporting_period.current_start
#     current_end = reporting_period.current_end
#     previous_start = reporting_period.previous_start
#     previous_end = reporting_period.previous_end
#     period_label = reporting_period.label
#     period_key = reporting_period.file_key
    
#     logger.info(f"리포트 생성 기간: {period_label}")
#     logger.info(f"현재 기간: {current_start.strftime('%Y-%m-%d %H:%M:%S')} ~ {current_end.strftime('%Y-%m-%d %H:%M:%S')}")
#     logger.info(f"비교 기간: {previous_start.strftime('%Y-%m-%d %H:%M:%S')} ~ {previous_end.strftime('%Y-%m-%d %H:%M:%S')}")
    
#     metrics_interval_seconds = max(interval_minutes, 1) * 60
#     logger.info(f"Cloud Insight 조회 간격: {interval_minutes}분 ({metrics_interval_seconds}초)")
    
#     # API 클라이언트 초기화
#     logger.info("API 클라이언트 초기화 중...")
    
#     # 모든 서비스는 동일한 통합 API 게이트웨이 사용
#     # 각 서비스별 경로는 API 호출 시 엔드포인트에 포함됨
#     api_client = NCPBaseClient(
#         access_key=NCP_ACCESS_KEY,
#         secret_key=NCP_SECRET_KEY,
#         base_url=API_ENDPOINTS['vserver']  # 일반 서비스용 base_url
#     )
    
#     # 쿠버네티스(NKS)는 별도의 게이트웨이 사용
#     k8s_client = NCPBaseClient(
#         access_key=NCP_ACCESS_KEY,
#         secret_key=NCP_SECRET_KEY,
#         base_url=API_ENDPOINTS['kubernetes']  # NKS 전용 base_url
#     )
    
#     # Cloud Insight는 별도의 게이트웨이 사용
#     cloud_insight_client = NCPBaseClient(
#         access_key=NCP_ACCESS_KEY,
#         secret_key=NCP_SECRET_KEY,
#         base_url=API_ENDPOINTS['monitoring']  # Cloud Insight 전용 base_url
#     )
    
#     # API 모듈 초기화
#     resource_api = ResourceAPI(api_client)
#     server_api = ServerAPI(api_client)
#     monitoring_api = MonitoringAPI(cloud_insight_client, cw_key=CLOUD_INSIGHT_CW_KEY)
#     storage_api = StorageAPI(api_client)
#     network_api = NetworkAPI(api_client)
#     k8s_api = KubernetesAPI(k8s_client)  # NKS 전용 클라이언트 사용
    
#     # 수집기 및 분석기 초기화
#     resource_summary_collector = ResourceSummaryCollector(
#         resource_api=resource_api,
#         server_api=server_api,
#         storage_api=storage_api,
#         network_api=network_api,
#         k8s_api=k8s_api
#     )
    
#     data_collector = DataCollector(
#         server_api=server_api,
#         monitoring_api=monitoring_api,
#         storage_api=storage_api,
#         k8s_api=k8s_api
#     )
    
#     data_analyzer = DataAnalyzer()
    
#     report_generator = ReportGenerator(output_dir=REPORT_OUTPUT_DIR)
    
#     # 1. 리소스 요약 수집
#     logger.info("\n[1단계] 리소스 요약 정보 수집 중...")
#     resource_summary = resource_summary_collector.collect(region_code=NCP_REGION)
    
#     # 2. 서버 메트릭 수집
#     logger.info("\n[2단계] 서버 메트릭 수집 중...")
#     server_list_response = resource_api.get_server_list(region_code=NCP_REGION)
#     logger.debug(f"서버 목록 응답 키: {list(server_list_response.keys())}")
    
#     # 응답 구조 확인 및 파싱
#     if 'getServerInstanceListResponse' in server_list_response:
#         response_data = server_list_response['getServerInstanceListResponse']
#         servers = response_data.get('serverInstanceList', [])
#         logger.info(f"서버 목록 - totalRows: {response_data.get('totalRows', 'N/A')}, returnCode: {response_data.get('returnCode', 'N/A')}")
#     else:
#         servers = server_list_response.get('serverInstanceList', [])
#         if not servers:
#             for key, value in server_list_response.items():
#                 if isinstance(value, dict) and 'serverInstanceList' in value:
#                     servers = value['serverInstanceList']
#                     break
    
#     current_server_metrics = []
#     previous_server_metrics = []
    
#     for server in servers:
#         server_instance_no = server.get('serverInstanceNo')
#         zone_code = server.get('zoneCode', '')
        
#         if not server_instance_no:
#             continue
        
#         try:
#             # 현재 달 메트릭 수집
#             current_metrics = data_collector.collect_server_metrics(
#                 server_instance_no=server_instance_no,
#                 zone_code=zone_code,
#                 start_time=current_start,
#                 end_time=current_end,
#                 region_code=NCP_REGION,
#                 period=metrics_interval_seconds
#             )
#             current_server_metrics.append(current_metrics)
            
#             # 이전 달 메트릭 수집
#             previous_metrics = data_collector.collect_server_metrics(
#                 server_instance_no=server_instance_no,
#                 zone_code=zone_code,
#                 start_time=previous_start,
#                 end_time=previous_end,
#                 region_code=NCP_REGION,
#                 period=metrics_interval_seconds
#             )
#             previous_server_metrics.append(previous_metrics)
            
#         except Exception as e:
#             logger.error(f"서버 {server_instance_no} 메트릭 수집 중 오류: {e}")
    
#     # 3. NAS 메트릭 수집
#     logger.info("\n[3단계] NAS 메트릭 수집 중...")
#     nas_list_response = resource_api.get_nas_list(region_code=NCP_REGION)
#     nas_list = nas_list_response.get('getNasVolumeInstanceListResponse', {}).get('nasVolumeInstanceList', [])
    
#     current_nas_metrics = []
#     previous_nas_metrics = []
    
#     for nas in nas_list:
#         nas_instance_no = nas.get('nasVolumeInstanceNo')
        
#         if not nas_instance_no:
#             continue
        
#         try:
#             # 현재 사용률 수집
#             current_metrics = data_collector.collect_nas_metrics(
#                 nas_instance_no=nas_instance_no,
#                 region_code=NCP_REGION
#             )
#             current_nas_metrics.append(current_metrics)
            
#             # 이전 달 사용률은 동일한 API로 수집 (실제로는 이전 달 데이터가 필요할 수 있음)
#             previous_metrics = data_collector.collect_nas_metrics(
#                 nas_instance_no=nas_instance_no,
#                 region_code=NCP_REGION
#             )
#             previous_nas_metrics.append(previous_metrics)
            
#         except Exception as e:
#             logger.error(f"NAS {nas_instance_no} 메트릭 수집 중 오류: {e}")
    
#     # 4. 쿠버네티스 메트릭 수집
#     logger.info("\n[4단계] 쿠버네티스 메트릭 수집 중...")
#     cluster_list_response = k8s_api.get_cluster_list(region_code=NCP_REGION)
#     logger.debug(f"쿠버네티스 클러스터 응답 키: {list(cluster_list_response.keys())}")
    
#     # 응답 구조 확인 및 파싱
#     if 'getClusterListResponse' in cluster_list_response:
#         response_data = cluster_list_response['getClusterListResponse']
#         clusters = response_data.get('clusterList', [])
#     elif 'clusterList' in cluster_list_response:
#         clusters = cluster_list_response['clusterList']
#     else:
#         clusters = []
#         for key, value in cluster_list_response.items():
#             if isinstance(value, dict) and 'clusterList' in value:
#                 clusters = value['clusterList']
#                 break
#             elif isinstance(value, list):
#                 clusters = value
#                 break
    
#     current_k8s_metrics = []
    
#     for cluster in clusters:
#         cluster_uuid = cluster.get('clusterUuid')
        
#         if not cluster_uuid:
#             continue
        
#         try:
#             # 현재 달 메트릭 수집
#             cluster_metrics = data_collector.collect_k8s_metrics(
#                 cluster_uuid=cluster_uuid,
#                 start_time=current_start,
#                 end_time=current_end,
#                 region_code=NCP_REGION,
#                 period=metrics_interval_seconds
#             )
#             current_k8s_metrics.append(cluster_metrics)
            
#         except Exception as e:
#             logger.error(f"쿠버네티스 클러스터 {cluster_uuid} 메트릭 수집 중 오류: {e}")
    
#     # 5. 데이터 분석
#     logger.info("\n[5단계] 데이터 분석 중...")
#     analyzed_data = data_analyzer.analyze_all(
#         current_server_metrics=current_server_metrics,
#         current_nas_metrics=current_nas_metrics,
#         current_k8s_metrics=current_k8s_metrics,
#         previous_server_metrics=previous_server_metrics,
#         previous_nas_metrics=previous_nas_metrics,
#         previous_k8s_metrics=None  # 쿠버네티스 이전 달 데이터는 생략
#     )
    
#     # 6. 리포트 생성
#     logger.info("\n[6단계] 리포트 생성 중...")
    
#     html_file = report_generator.generate_html_report(
#         resource_summary=resource_summary,
#         server_metrics=analyzed_data['server_metrics'],
#         nas_metrics=analyzed_data['nas_metrics'],
#         k8s_metrics=analyzed_data['k8s_metrics'],
#         period_label=period_label,
#         period_key=period_key
#     )
    
#     excel_file = report_generator.generate_excel_report(
#         resource_summary=resource_summary,
#         server_metrics=analyzed_data['server_metrics'],
#         nas_metrics=analyzed_data['nas_metrics'],
#         k8s_metrics=analyzed_data['k8s_metrics'],
#         period_label=period_label,
#         period_key=period_key
#     )
    
#     logger.info("\n" + "=" * 60)
#     logger.info("리포트 생성 완료!")
#     logger.info(f"HTML 리포트: {html_file}")
#     logger.info(f"Excel 리포트: {excel_file}")
#     logger.info("=" * 60)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='네이버 클라우드 플랫폼 월간 리포트 생성 프로그램')
    parser.add_argument('--year', type=int, help='리포트를 생성할 년도 (기본값: 현재 년도)')
    parser.add_argument('--month', type=int, help='리포트를 생성할 월 (기본값: 현재 월)')
    parser.add_argument('--range', dest='range_type', choices=['previous_day', 'previous_week', 'previous_month', 'custom'], default='previous_month', help='보고 기간 유형 선택')
    parser.add_argument('--start-date', help='커스텀 기간 시작일 (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='커스텀 기간 종료일 (YYYY-MM-DD)')
    parser.add_argument('--interval-minutes', type=int, default=15, help='Cloud Insight 조회 간격(분)')
    
    args = parser.parse_args()
    
    main(
        year=args.year,
        month=args.month,
        range_type=args.range_type,
        start_date=args.start_date,
        end_date=args.end_date,
        interval_minutes=args.interval_minutes
    )

