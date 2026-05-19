"""
NAS 리소스 API 모듈

NAS 인스턴스 및 관련 정보를 조회하는 API 모듈입니다.
"""

from typing import Dict, List, Optional
from utils.common_rest import NCPBaseClient
from ncp_api.base import BaseNCPAPI


class VNasAPI(BaseNCPAPI):
    """
    NAS 리소스 API 클래스
    
    NAS 인스턴스 및 관련 정보를 조회합니다.
    """
    """
    ================================================================
    NAS 인스턴스 관련 API
    ================================================================
    """
    def get_nas_volume_instance_list(
        self,
        region_code: Optional[str] = None,
        zone_code: Optional[str] = None,
        nas_volume_instance_no_list: Optional[List[str]] = None,
        volume_name: Optional[str] = None,
        volume_allotment_protocol_type_code: Optional[str] = None,
        is_event_configuration: Optional[bool] = None,
        is_snapshot_configuration: Optional[bool] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
        
    ) -> Dict:
        """
        NAS 볼륨 인스턴스 목록을 조회합니다.
        
        Args:
            str region_code: 리전 코드(선택사항)
            str zone_code: 존 코드
            str nas_volume_instance_no_list: NAS 볼륨 인스턴스 번호 리스트
            str volume_name: 볼륨 이름
            str volume_Allotment_Protocol_Type_Code: 볼륨 할당 프로토콜 타입 코드
            str is_event_Configuration: 이벤트 설정 여부
            str is_snapshot_Configuration: 스냅샷 설정 여부
            int page_no: 페이지 번호
            int page_size: 페이지당 항목 수
            str sort_by: 정렬 기준 (예: nasVolumeInstanceNo | volumeName | volumeTotalSize |nasVolumeInstanceNo: NAS 볼륨 인스턴스 번호 | volumeName: 볼륨 이름 |volumeTotalSize: 볼륨 총 크기 )
            str sort_order: 정렬 순서 ('asc' 또는 'desc')
        
        Returns:
            Dict: NAS 볼륨 인스턴스 목록 응답
        """
        params = {}             

        if region_code is not None:
            params['regionCode'] = region_code
        if zone_code is not None:
            params['zoneCode'] = zone_code
        if nas_volume_instance_no_list is not None:
            for idx, nas_volume_instance_no in enumerate(nas_volume_instance_no_list, start=1):
                params[f'nasVolumeInstanceNoList.{idx}'] = nas_volume_instance_no
        if volume_name is not None:
            params['volumeName'] = volume_name
        if volume_allotment_protocol_type_code is not None:
            params['volumeAllotmentProtocolTypeCode'] = volume_allotment_protocol_type_code
        if is_event_configuration is not None:
            params['isEventConfiguration'] = is_event_configuration
        if is_snapshot_configuration is not None:
            params['isSnapshotConfiguration'] = is_snapshot_configuration
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if sort_by is not None:
            params['sortBy'] = sort_by
        if sort_order is not None:
            params['sortOrder'] = sort_order
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType  # JSON 형식 명시
        
        return self.get('/getNasVolumeInstanceList', params=params)

    def get_nas_volume_instance_detail(
        self,
        nas_volume_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        NAS 볼륨 인스턴스 상세 정보를 조회합니다.
    
        Args:
            str nas_volume_instance_no: NAS 볼륨 인스턴스 번호
            str region_code: 리전 코드(선택사항)
        
        Returns:
            Dict: NAS 볼륨 인스턴스 상세 정보 응답
        """
        params = {
            'nasVolumeInstanceNo': nas_volume_instance_no            
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType  # JSON 형식 명시
        return self.get('/getNasVolumeInstanceDetail', params=params)

    def get_nas_volume_access_control_rule_list(
        self,
        nas_volume_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        NAS 볼륨 인스턴스에 설정된 접근 제어 규칙 목록을 조회합니다.
        
        Args:
            str nas_volume_instance_no: NAS 볼륨 인스턴스 번호
            str region_code: 리전 코드(선택사항)
        
        Returns:
            Dict: NAS 볼륨 인스턴스에 설정된 접근 제어 규칙 목록 응답
        """
        params = {
            'nasVolumeInstanceNo': nas_volume_instance_no
            
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType  # JSON 형식 명시
        return self.get('/getNasVolumeAccessControlRuleList', params=params)
    
    

    def get_nas_volume_instance_rating_list(
        self,
        nas_volume_instance_no: str,
        start_time: str,
        end_time: str,
        interval: str,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        특정 기간의 NAS 볼륨 인스턴스의 크기를 설정한 측정 간격에 따라 조회합니다.
        
        Args:
            str nas_volume_instance_no: NAS 볼륨 인스턴스 번호
            str start_time: 시작 시간 (yyyy-MM-dd'T'HH:mm:ssZ)(<예시> 2024-04-01'T'00:00:00+0900)(GET 방식 이용 시 URL 인코딩 필요)
            str end_time: 종료 시간 (yyyy-MM-dd'T'HH:mm:ssZ)(<예시> 2024-04-01'T'00:00:00+0900)(GET 방식 이용 시 URL 인코딩 필요)
            str interval: 측정 간격 (5m: 5분, 6h: 6시간, 1d: 1일, 1M: 1개월) 제약조건(5m: 최대 3일, 6h: 최대 1개월, 1d: 최대 2년, 1M: 최대 5년)
            str region_code: 리전 코드(선택사항)
        
        Returns:
        """
        params = {
            'nasVolumeInstanceNo': nas_volume_instance_no,
            'startTime': start_time,
            'endTime': end_time,
            'interval': interval
            
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType  # JSON 형식 명시

        return self.get('/getNasVolumeInstanceRatingList', params=params)



    """
    ================================================================
    NAS 볼륨 스냅샷 관련 API
    ================================================================
    """
    def get_nas_volume_snapshot_configuration_history_list(
        self,
        nas_volume_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        NAS 볼륨 인스턴스의 스냅샷 설정 이력을 조회할 수 있습니다.
        
        Args:
            str nas_volume_instance_no: NAS 볼륨 인스턴스 번호
            str region_code: 리전 코드(선택사항)
        
        Returns:
            Dict: NAS 볼륨 인스턴스의 스냅샷 설정 이력 응답
        """
        params = {
            'nasVolumeInstanceNo': nas_volume_instance_no
            
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType  # JSON 형식 명시

        return self.get('/getNasVolumeSnapshotConfigurationHistoryList', params=params)

    def get_nas_volume_snapshot_list(
            self,
            nas_volume_instance_no: str,
            region_code: Optional[str] = None,
            responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        NAS 볼륨 인스턴스의 스냅샷 목록을 조회합니다.
            
        Args:
            str nas_volume_instance_no: NAS 볼륨 인스턴스 번호
            str region_code: 리전 코드(선택사항)
                
        Returns:
            Dict: NAS 볼륨 인스턴스의 스냅샷 목록 응답
        """
        params = {
            'nasVolumeInstanceNo': nas_volume_instance_no
            
        }
        
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType  # JSON 형식 명시
        return self.get('/getNasVolumeSnapshotList', params=params)