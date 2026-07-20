"""
Global DNS 리소스 API 모듈

Global DNS 인스턴스 및 관련 정보를 조회하는 API 모듈입니다.



"""

from bisect import insort_right
from typing import Dict, List, Optional
from ncp_api.base import BaseNCPAPI



class GlobaldnsAPI(BaseNCPAPI):
    """
    Global DNS 리소스 API 클래스

    Global DNS 인스턴스 및 관련 정보를 조회합니다.
    """
    ENDPOINT_KEY = "globaldns"


    """
    ================================================================
    Global DNS 관련 API
    Untested code, need to be checked properly
    ================================================================
    """

    def get_dns_domain_query(
        self,
        base_time_unix: str,
        domain_id: Optional[int] = None
    ) -> Dict:
        """
        Global DNS 도메인 쿼리를 조회합니다.

        args:
            str base_time_unix: 시간 간격 (MINUTE_1 | MINUTE_5 | MINUTE_30 | HOUR_3 | DAY_1)
            int domain_id: 도메인 ID
            responseFormatType: 응답 형식(json, xml)

        Returns:
            Dict: Global DNS 도메인 쿼리 응답
        """
        params = { 
            'baseTimeUnix': base_time_unix,
            
        }
        if domain_id is not None:
            params['domainId'] = domain_id
        return self.client.get('/ncpdns/domain/monitoring', params=params)

    def get_lb_record(
        self,
        platform_type : str,
        record_type : str,
        search_content : Optional[str] = None,
        lb_region_code : Optional[str] = None
    ) -> Dict:
        """
        지정한 조건을 만족하는 Global DNS 로드밸런서 레코드 정보를 조회합니다.

        args:
            str platform_type: 플랫폼 타입 (VPC | CLASSIC)
            str record_type: 레코드 타입 (A | AAAA | CNAME | MX | PTR | SPF | TXT | NS | SRV | CAA | DS)
            str search_content: 조회할 로드벨런서 레코드 (선택사항)
            str lb_region_code: 로드밸런서 레코드 리전 (선택사항)

        Returns:
            Dict: Global DNS 로드밸런서 레코드 정보 응답
        """
        params = {}
        if search_content is not None:
            params['searchContent'] = search_content    
        if lb_region_code is not None:
            params['lbRegionCode'] = lb_region_code
        return self.client.get(f'/ncpdns/lb-record/{platform_type}/{record_type}', params=params)

    def get_domain_detail(
        self,
        domain_id : int
    ) -> Dict:
        """
        Global DNS 도메인 상세 정보를 조회합니다.

        args:
            int domain_id: 도메인 ID

        Returns:
            Dict: Global DNS 도메인 상세 정보 응답
        """
        
        params = {}
        return self.client.get(f'/ncpdns/domain/{domain_id}', params=params)

    def get_domain(
        self,
        page : int,
        size : int, 
        domain_name : Optional[str] = None
    ) -> Dict:
        """
        지정한 조건에 따라 도메인 정보를 조회합니다.

        args:
            int page: 페이지 번호
            int size: 페이지 크기
            str domain_name: 도메인 이름 (선택사항)

        Returns:
            Dict: Global DNS 도메인 정보 응답
        """
        params = {  
            'page': page,
            'size': size
        }
        if domain_name:
            params['domainName'] = domain_name
        return self.client.get('/ncpdns/domain', params=params)
    
    def get_record(
        self,
        page : int,
        size : int,
        domain_id : str,
        record_type : Optional[str] = None,
        search_content : Optional[str] = None
    ) -> Dict:
        """
        지정한 조건에 따라 레코드 정보를 조회합니다.
    
        args:
            str domain_id: 도메인 ID
            int page: 페이지 번호
            int size: 페이지 크기
            str record_type: 레코드 타입 (A | AAAA | CNAME | MX | PTR | SPF | TXT | NS | SRV | CAA | DS) (선택사항)
            str search_content: 레코드 이름을 기준으로 검색 (선택사항)


        Returns:
            Dict: Global DNS 도메인 레코드 응답
        """
        params = {
            'domainId': domain_id,
            'page' : page,
            'size' : size      
        }
        if record_type is not None:
            params['recordType'] = record_type
        if search_content is not None:
            params['searchContent'] = search_content
        
        return self.client.get(f'/ncpdns/record/{domain_id}', params=params)
