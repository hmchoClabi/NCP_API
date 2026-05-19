from typing import Dict, List, Optional
from utils.common_rest import NCPBaseClient


class CloudLogAnalyticsAPI:
    """
    Cloud Log Analytics API 클래스

    """
    
    def __init__(self, client: NCPBaseClient):
        """
        Cloud Log Analytics API를 초기화합니다.
        
        Args:
            client: NCPBaseClient 인스턴스
        """
        self.client = client
    """
    ================================================================
    서버 목록 관련 API
    ================================================================
    """
        
    def get_cla_server_list(
        self,
        region_code : str,
        svr_type : str = 'vm',
        page_no : Optional[int] = None,
        page_size : Optional[int] = None
        
    ) -> Dict:
        """
        VPC 환경의 서버 인스턴스(VM) 목록을 조회하고, 서버별 Cloud Log Analytics 서비스를 통한 로그 수집 설정 상태를 확인합니다.

        args:
            str regionCode: 지역 코드 (예: kr, sgn, jp 등)
            int page_no: 페이지 
            int page_size: 페이지 사이즈
            svr_type: 조회서버 타입 (임의추가)  (vm | cdb4my | cdb4mongo | cdb4postgre | bm | nks | ses (search engine service) | cdss (cloud data streaming service) )
        Returns:
            Dict: 서버 인스턴스 정보보
                
        """
        params = {}
        uri = ''
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size

        if svr_type == 'vm':
            uri = ''
        elif svr_type == 'cdbmy':
            uri = '/mysql'
        elif svr_type == 'cdb4mongo':
            uri = '/mongodb'
        elif svr_type == 'cdb4postgre':
            uri = '/postgresql'
        elif svr_type == 'bm':
            uri = '/baremetal'
        elif svr_type == 'nks':
            uri = '/kubernetes'
        elif svr_type == 'ses':
            uri = '/ses'
        elif svr_type == 'cdss':
            uri = '/cdss'
        else:
            raise ValueError(f'Unsupported svr_type: {svr_type}')


        return self.client.get(f'/api/{region_code}-v1/vpc/servers{uri}', params=params)
    """
    ================================================================
    로그 관련 API
    ================================================================
    """
    def get_cla_log_count_total(
        self,
        region_code : str
    ) -> Dict:
        """
        Cloud Log Analytics 서비스에서 수집한 전체 로그 수를 조회합니다.

        args:
            str regionCode: 지역 코드 (예: kr, sgn, jp 등)
 
            
        Returns:
            Dict: Cloud Log Analytics 서비스에서 수집한 전체 로그 수
        """
        params = {}

        return self.client.get(f'/api/{region_code}-v1/logs/count/total', params=params)
    
    def get_cla_log_count_recent(
        self,
        region_code : str
    ) -> Dict:
        """
        Cloud Log Analytics 서비스에서 최근 1분 동안 수집한 로그 수를 조회합니다.

        args:
            str regionCode: 지역 코드 (예: kr, sgn, jp 등)
 
            
        Returns:
            Dict: Cloud Log Analytics 서비스에서 최근 1분 동안 수집한 로그 수
        """
        params = {}

        return self.client.get(f'/api/{region_code}-v1/logs/count/recent', params=params)
    
    def get_cla_log_count_interval(
        self,
        region_code : str,
        start_time : Optional[str] = None,
        end_time : Optional[str] = None,
        interval : Optional[str] = None
    ) -> Dict:
        """
        Cloud Log Analytics 서비스에서 조회 기간 동안 수집한 로그 수를 특정 주기 기준으로 조회합니다.

        args:
            str regionCode: 지역 코드 (예: kr, sgn, jp 등)
            str start_time : 조회시작일시 (unix timestamp now-1h기본)
            str end_time : 조회종료일시 (unix timestamp now-1h기본)
            str interval : 조회주기 (now-1d기본본)
 
            
        Returns:
            Dict: Cloud Log Analytics 서비스에서 특정주기 동안안 수집한 로그 수
        """
        params = {}

        if start_time is not None:
            params['startTime'] = start_time
        if end_time is not None:
            params['endTime'] = end_time
        if interval is not None:
            params['interval'] = interval

        return self.client.get(f'/api/{region_code}-v1/logs/count/interval', params=params)
    
    def get_cla_log_count_aggregation(
        self,
        region_code : str,
        type : Optional[str] = None
    ) -> Dict:
        """
        Cloud Log Analytics 서비스에서 수집한 로그 수를 서버 로그 유형별로 조회합니다.

        args:
            str regionCode: 지역 코드 (예: kr, sgn, jp 등)
            str type : 조회기준 (server | log_name)
            
        Returns:
            Dict: Cloud Log Analytics 서비스에서 수집한 로그 수를 서버 로그 유형별로 조회합니다.
        """
        params = {}

        return self.client.get(f'/api/{region_code}-v1/logs/count/aggregation', params=params)

    def get_cla_log_search(
        self,
        region_code : str,
        interval : Optional[str] = None, 
        keyword :  Optional[str] = None, 
        log_types : Optional[str] = None, 
        timestamp_from : Optional[str] = None,
        timestamp_to : Optional[str] = None,
        page_no : Optional[int] = None,
        page_size : Optional[int] = None
    ) -> Dict:
        """
        Cloud Log Analytics 서비스에서 수집한 로그를 조회합니다.

        args:
            str regionCode: 지역 코드 (예: kr, sgn, jp 등)
            str interval : 조회 주기 (기본 5m | 1d | 1h | 1m)
            str keyword :  조회 키워드
            str log_types : 로그 유형 ( SYSLOG | security_log | tomcat | ... )
            str timestamp_from : 조회시작일시 (unix timestamp)
            str timestamp_to : 조회종료료일시 (unix timestamp)
            int page_no: 페이지 
            int page_size: 페이지 사이즈
            
        Returns:
            Dict: 조회된 로그 정보
                
        """
        json_body = {}
        
        
        if page_no is not None:
            json_body['pageNo'] = page_no
            
        if interval is not None:
            json_body['interval'] = interval
            
        if keyword is not None:
            json_body['keyword'] = keyword
            
        if log_types is not None:
            json_body['logTypes'] = log_types
            
        if timestamp_from is not None:
            json_body['timestampFrom'] = timestamp_from

        if timestamp_to is not None:
            json_body['timestampTo'] = timestamp_to

        if page_no is not None:
            json_body['pageNo'] = page_no
        if page_size is not None:
            json_body['pageSize'] = page_size

        


        return self.client.post(f'/api/{region_code}-v1/logs/search', json_data=json_body)
    


    def get_cla_log_capacity(
        self,
        region_code : str
    ) -> Dict:
        """
        Cloud Log Analytics 서비스에서 사용 중인 용량을 조회합니다.

        args:
            str regionCode: 지역 코드 (예: kr, sgn, jp 등)
 
            
        Returns:
            Dict: Cloud Log Analytics 서비스에서 사용 중인 용량량
        """
        params = {}

        return self.client.get(f'/api/{region_code}-v1/capacity', params=params)
    

