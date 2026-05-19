"""
설정 파일 모듈

네이버 클라우드 플랫폼 API 인증 정보 및 설정을 관리합니다.
"""

import os
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# .env 파일 로드
# 프로젝트 루트 디렉토리 기준으로 .env 파일 경로 지정
project_root = Path(__file__).parent.parent
possible_env_paths = [
    project_root / '.env',  # 프로젝트 루트
    Path('.env'),  # 현재 작업 디렉토리
    Path(os.getcwd()) / '.env',  # 명시적 현재 디렉토리
]

env_file_path = None
result = False

# 모든 가능한 경로에서 .env 파일 찾기
for env_path in possible_env_paths:
    if env_path.exists():
        env_file_path = str(env_path)
        # print(f"[DEBUG] .env 파일을 찾았습니다: {env_path}")
        
        # 방법 1: load_dotenv() 사용
        result = load_dotenv(dotenv_path=env_file_path, override=True)
        # print(f"[DEBUG] load_dotenv() 반환값: {result}")
        break

if not env_file_path:
#     # 기본적으로 현재 디렉토리에서 찾기 시도
    result = load_dotenv(override=True)
    # print(f"[DEBUG] .env 파일을 찾을 수 없습니다. 다음 경로를 확인했습니다:")
    # for path in possible_env_paths:
    #     print(f"[DEBUG]   - {path} (존재: {path.exists()})")
    # print(f"[DEBUG] 현재 작업 디렉토리: {os.getcwd()}")
    # print(f"[DEBUG] load_dotenv() 반환값: {result}")

# # .env 파일 직접 읽기 및 파싱 (백업 방법)
# # load_dotenv()가 실패하거나 env_file_path가 없어도 모든 경로 시도

parsed_count = 0
for env_path in possible_env_paths:
    if env_path.exists():
        try:
            # print(f"[DEBUG] 직접 파싱 시도: {env_path}")
            file_size = env_path.stat().st_size
            # print(f"[DEBUG] .env 파일 크기: {file_size} bytes")
            
            if file_size == 0:
                print(f"경고: .env 파일이 비어있습니다!")
                #print(f".env 파일에 다음 형식으로 내용을 추가해주세요:")
                #print(f"NCP_ACCESS_KEY=your_access_key")
                #print(f"NCP_SECRET_KEY=your_secret_key")
                #print(f"NCP_REGION=KR")
                continue
            
            with open(env_path, 'r', encoding='utf-8-sig') as f:  # BOM 제거
                lines = f.readlines()
                # print(f"[DEBUG] .env 파일 라인 수: {len(lines)}")
                
                # 원본 라인도 출력 (디버깅용)
                # if lines:
                    # print(f"[DEBUG] 원본 라인들:")
                    # for i, line in enumerate(lines[:10], 1):  # 처음 10줄만
                        # print(f"[DEBUG]   라인 {i}: {repr(line)}")
                
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    # 주석이나 빈 줄 건너뛰기
                    if not stripped or stripped.startswith('#'):
                        continue
                    
                    # 등호로 분리
                    if '=' in stripped:
                        key, value = stripped.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # 따옴표 제거 (있는 경우)
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]
                        
                        # 환경 변수 설정 (직접 설정)
                        if key and value:
                            os.environ[key] = value
                            parsed_count += 1
                            print(f"직접 파싱 성공: {key}=[값 길이: {len(value)}]")
                    else:
                        print(f"등호가 없는 라인 {i}: {stripped[:50]}")
                
                if parsed_count > 0:
                    # print(f"[DEBUG] 총 {parsed_count}개의 환경 변수를 직접 파싱했습니다.")
                    break  # 성공하면 다른 경로 시도하지 않음
        except Exception as e:
            print(f"{env_path} 직접 읽기 오류: {e}")
            import traceback
            traceback.print_exc()

# 네이버 클라우드 플랫폼 API 인증 정보
# 환경 변수에서 로드하거나 직접 설정 가능
NCP_ACCESS_KEY = os.getenv('NCP_ACCESS_KEY', '')
NCP_SECRET_KEY = os.getenv('NCP_SECRET_KEY', '')

# 디버깅: 환경 변수 로드 확인
if NCP_ACCESS_KEY:
    print(f"NCP_ACCESS_KEY가 로드되었습니다 (길이: {len(NCP_ACCESS_KEY)})")
else:
    print("[DEBUG] NCP_ACCESS_KEY가 로드되지 않았습니다.")


# NCP 리전 설정
NCP_REGION = os.getenv('NCP_REGION', 'KR')

# Cloud Insight 프로덕트 키 (cw_key, prodKey)
# Cloud Insight API를 사용하려면 이 값이 필요합니다
CLOUD_INSIGHT_CW_KEY = os.getenv('CLOUD_INSIGHT_CW_KEY', '')


# Cloud Insight Product Name (기본값: "Server(VPC)" 또는 "System/Server(VPC)")
# 실제 사용 가능한 상품명은 Cloud Insight 콘솔에서 확인해야 합니다
CLOUD_INSIGHT_PRODUCT_NAME = os.getenv('CLOUD_INSIGHT_PRODUCT_NAME', 'Server(VPC)')

# Cloud Insight 메트릭 이름 설정 (선택사항)
# 기본값은 문서 예시를 따르지만, 실제 사용 가능한 메트릭 이름은 콘솔에서 확인해야 합니다
CLOUD_INSIGHT_CPU_METRIC = os.getenv('CLOUD_INSIGHT_CPU_METRIC', 'avg_cpu_used_rto')
CLOUD_INSIGHT_MEMORY_METRIC = os.getenv('CLOUD_INSIGHT_MEMORY_METRIC', 'mem_usert')
CLOUD_INSIGHT_DISK_METRIC = os.getenv('CLOUD_INSIGHT_DISK_METRIC', 'fs_usert')

# NCP API 타입 설정 (public: 민간용, gov: 정부용)
NCP_API_TYPE = os.getenv('NCP_API_TYPE', 'public').lower()

# API 엔드포인트 설정
# 정부용과 민간용에 따라 다른 엔드포인트 사용
if NCP_API_TYPE == 'gov':
    API_BASE_URL = 'https://ncloud.apigw.gov-ntruss.com'
    BILLING_API_BASE_URL = 'https://billingapi.apigw.gov-ntruss.com/billing/v1'
    CLOUD_INSIGHT_BASE_URL = 'https://cw.apigw.gov-ntruss.com'
    
    if NCP_REGION == 'KRS':   #남부 리전
        CONTAINER_REGISTRY_BASE_URL = 'https://gov-ncr.apigw.gov-ntruss.com/ncr/krs'
        NKS_BASE_URL = 'https://nks.apigw.gov-ntruss.com/vnks/krs-v2'
    else:
        CONTAINER_REGISTRY_BASE_URL = 'https://gov-ncr.apigw.gov-ntruss.com/ncr/kr'
        NKS_BASE_URL = 'https://nks.apigw.gov-ntruss.com/vnks/v2'
    LB_BASE_URL = 'https://ncloud.apigw.gov-ntruss.com/vloadbalancer/v2'
    NAS_BASE_URL = 'https://ncloud.apigw.gov-ntruss.com/vnas/v2'
    RESOURCE_MANAGER_BASE_URL = 'https://resourcemanager.apigw.gov-ntruss.com'
    VPC_BASE_URL = 'https://ncloud.apigw.gov-ntruss.com/vpc/v2'
    CLA_BASE_URL = 'https://cloudloganalytics.apigw.gov-ntruss.com'
    SUBACCOUNT_BASE_URL = 'https://subaccount.apigw.gov-ntruss.com'
    WMS_BASE_URL = 'https://wms.apigw.gov-ntruss.com'
    GLOBAL_DNS_BASE_URL = 'https://globaldns.apigw.gov-ntruss.com/dns/v1'
    CLOUD_INSIGHT_BASE_URL = 'https://cw.apigw.gov-ntruss.com'
    CLOUD_ACTIVITY_TRACER_BASE_URL = 'https://cloudactivitytracer.apigw.gov-ntruss.com'
    SECURITY_MONITORING_BASE_URL = 'https://securitymonitoring.apigw.gov-ntruss.com'
    CERTIFICATE_MANAGER_BASE_URL = 'https://certificatemanager.apigw.gov-ntruss.com'
    #SYSTEM_SERVER_VPC_CW_KEY = os.getenv('GOV_CLOUD_INSIGHT_CW_KEY', '567435234753253376')  # 정부용 vServer 기본값
    #SYSTEM_NKS_CW_KEY = os.getenv('GOV_NKS_CW_KEY', '769285093356343296')  # 정부용 NKS 기본값
    print(f"정부용(GOV) API 엔드포인트 사용: {API_BASE_URL}")
    print(f"정부용(GOV) NKS 엔드포인트 사용: {NKS_BASE_URL}")
    print(f"정부용(GOV) Cloud Insight 엔드포인트 사용: {CLOUD_INSIGHT_BASE_URL}")
else:
    API_BASE_URL = 'https://ncloud.apigw.ntruss.com'
    BILLING_API_BASE_URL = 'https://billingapi.apigw.ntruss.com/billing/v1'
    if NCP_REGION == 'SGN':   #싱가포르리전
        CONTAINER_REGISTRY_BASE_URL = 'https://ncr.apigw.ntruss.com/ncr/sgn-api/v2'
        NKS_BASE_URL = 'https://nks.apigw.ntruss.com/vnks/sgn-v2'
    elif NCP_REGION == 'JPN':   #일본리전
        CONTAINER_REGISTRY_BASE_URL = 'https://ncr.apigw.ntruss.com/ncr/jpn-api/v2'
        NKS_BASE_URL = 'https://nks.apigw.ntruss.com/vnks/jpn-v2'
    else: #한국리전
        CONTAINER_REGISTRY_BASE_URL = 'https://ncr.apigw.ntruss.com/ncr/api/v2'
        NKS_BASE_URL = 'https://nks.apigw.ntruss.com/vnks/v2'
        #NCP_STORAGE_TEMPLATE_BASE_URL = 'https://{bucketName}.{regionCode}.ncloudstorage.com'
    LB_BASE_URL = 'https://ncloud.apigw.ntruss.com/vloadbalancer/v2'
    NAS_BASE_URL = 'https://ncloud.apigw.ntruss.com/vnas/v2'
    RESOURCE_MANAGER_BASE_URL = 'https://resourcemanager.apigw.ntruss.com'
    VPC_BASE_URL = 'https://ncloud.apigw.ntruss.com/vpc/v2'
    CLA_BASE_URL = 'https://cloudloganalytics.apigw.ntruss.com'
    SUBACCOUNT_BASE_URL = 'https://subaccount.apigw.ntruss.com'
    WMS_BASE_URL = 'https://wms.apigw.ntruss.com'
    GLOBAL_DNS_BASE_URL = 'https://globaldns.apigw.ntruss.com/dns/v1'
    CLOUD_INSIGHT_BASE_URL = 'https://cw.apigw.ntruss.com'
    CLOUD_ACTIVITY_TRACER_BASE_URL = 'https://cw.apigw.ntruss.com'
    SECURITY_MONITORING_BASE_URL = 'https://securitymonitoring.apigw.ntruss.com'
    CERTIFICATE_MANAGER_BASE_URL = 'https://certificatemanager.apigw.ntruss.com/api/v1'
    #SYSTEM_SERVER_VPC_CW_KEY = os.getenv('CLOUD_INSIGHT_CW_KEY', '460438474722512896')  # 민간용 vServer 기본값
    #SYSTEM_NKS_CW_KEY = os.getenv('NKS_CW_KEY', '526115048926613504')  # 민간용 NKS 기본값
    print(f"민간용(PUBLIC) API 엔드포인트 사용: {API_BASE_URL}")
    print(f"민간용(PUBLIC) NKS 엔드포인트 사용: {NKS_BASE_URL}")
    print(f"민간용(PUBLIC) Cloud Insight 엔드포인트 사용: {CLOUD_INSIGHT_BASE_URL}")

# API 엔드포인트 설정
# 쿠버네티스(NKS)는 별도의 게이트웨이 사용
API_ENDPOINTS: Dict[str, str] = {
    'server': API_BASE_URL,
    'vserver': API_BASE_URL,
    'container_registry': CONTAINER_REGISTRY_BASE_URL,
    'billing': BILLING_API_BASE_URL,
    'monitoring': CLOUD_INSIGHT_BASE_URL,  # Cloud Insight는 별도 게이트웨이
    'storage': API_BASE_URL,
    'vpc': API_BASE_URL,
    'loadbalancer': API_BASE_URL,
    'kubernetes': NKS_BASE_URL,  # NKS는 별도 게이트웨이
    'vnas': NAS_BASE_URL,
    'vpc' : VPC_BASE_URL,
    'lb' : LB_BASE_URL,
    'globaldns' : GLOBAL_DNS_BASE_URL,
    'resourcemanager' : RESOURCE_MANAGER_BASE_URL,
    'cla' : CLA_BASE_URL,
    'subaccount' : SUBACCOUNT_BASE_URL,
    'wms' : WMS_BASE_URL,
    'insight' : CLOUD_INSIGHT_BASE_URL,
    'tracer' : CLOUD_ACTIVITY_TRACER_BASE_URL,
    'securitymonitoring' : SECURITY_MONITORING_BASE_URL,
    'certificatemanager' : CERTIFICATE_MANAGER_BASE_URL
    }

# 리포트 출력 경로
REPORT_OUTPUT_DIR = os.getenv('REPORT_OUTPUT_DIR', './reports')

# 날짜 형식 설정
DATE_FORMAT = '%Y-%m-%d'
DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'

# 메트릭 수집 간격 (초)
METRICS_COLLECTION_INTERVAL = 3600  # 1시간

# API 요청 타임아웃 (초)
API_TIMEOUT = 30

# API 재시도 횟수
API_RETRY_COUNT = 3

# 리포트 형식 설정
REPORT_FORMATS = ['html', 'excel', 'pdf']  # 지원하는 리포트 형식

# 로깅 설정
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', './logs/ncp_report.log')

def get_config() -> Dict[str, Any]:
    """
    전체 설정을 딕셔너리로 반환합니다.
    
    Returns:
        Dict[str, Any]: 설정 정보 딕셔너리
    """
    return {
        'access_key': NCP_ACCESS_KEY,
        'secret_key': NCP_SECRET_KEY,
        'region': NCP_REGION,
        'endpoints': API_ENDPOINTS,
        'report_output_dir': REPORT_OUTPUT_DIR,
        'date_format': DATE_FORMAT,
        'datetime_format': DATETIME_FORMAT,
        'metrics_collection_interval': METRICS_COLLECTION_INTERVAL,
        'api_timeout': API_TIMEOUT,
        'api_retry_count': API_RETRY_COUNT,
        'report_formats': REPORT_FORMATS,
        'log_level': LOG_LEVEL,
        'log_file': LOG_FILE,
    }

