"""
    ResourceManager 리소스 API 모듈
"""

from bisect import insort_right
from typing import Dict, List, Optional
from utils.common_rest import NCPBaseClient
from ncp_api.base import BaseNCPAPI


class ResourceManagerAPI(BaseNCPAPI):
    """
    ResourceManager 리소스 API 클래스
    
    ResourceManager 인스턴스 및 관련 정보를 조회합니다.
    """
    """
    ================================================================
    리소스 매니져 관련 API
    ================================================================
    """
    def get_group_list(
        self,
        group_name: Optional[str] = None,
        page_index: Optional[int] = None,
        page_size: Optional[int] = None
    ) -> Dict:
        """
        리소스 매니져 그룹 목록을 조회합니다.

        args:
            str group_name: 그룹 이름 (선택사항)
            int page_index: 페이지 인덱스 (선택사항)
            int page_size: 페이지 크기 (선택사항)

        Returns:
            Dict: 리소스 매니져 그룹 목록 응답
        """
        params = {}

        if group_name:
            params['groupName'] = group_name
        if page_index:
            params['pageIndex'] = page_index
        if page_size:
            params['pageSize'] = page_size

        return self.get('/api/v1/groups', params=params)

    def get_resource_list(
        self,
        nrn : Optional[str] = None,
        product_name : Optional[str] = None,
        region_code : Optional[str] = None,
        resource_type : Optional[str] = None,
        resource_id : Optional[str] = None,
        resource_name : Optional[str] = None,
        tag : Optional[str] = None, 
        group_name : Optional[str] = None,
        page : Optional[int] = None,
        size : Optional[int] = None
    ) -> Dict:
        """
        리소스 목록을 조회합니다.
        args:
            str nrn:  네이버 클라우드 플랫폼 리소스 식별 값(선택사항)
            str product_name: 리소스의 서비스 코드 (선택사항)
            str region_code: 리전 코드 (선택사항)
            str resource_type: 리소스 유형 (선택사항)
            str resource_id: 리소스 아이디 (선택사항)
            str resource_name: 리소스 이름 (선택사항)
            str tag: 태그 (선택사항)
            str group_name: 그룹 이름 (선택사항)
            int page: 페이지 번호 (선택사항)
            int size: 페이지 크기 (선택사항)
        Returns:
            Dict: 리소스 목록 응답
        """
        params = {}
        if nrn:
            params['nrn'] = nrn
        if product_name:
            params['productName'] = product_name
        if region_code:
            params['regionCode'] = region_code
        if resource_type:
            params['resourceType'] = resource_type
        if resource_id:
            params['resourceId'] = resource_id
        if resource_name:
            params['resourceName'] = resource_name
        if tag:
            params['tag'] = tag
        if group_name:
            params['groupName'] = group_name
        if page:
            params['page'] = page
        if size:
            params['size'] = size

        return self.post('/api/v1/resources', json_data=params)