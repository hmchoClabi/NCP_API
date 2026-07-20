"""
컨테이너 리소스 API 모듈

컨테이너 인스턴스 및 관련 정보를 조회하는 API 모듈입니다.

Container Registry는 Docker Registry v2 스펙의 프라이빗 도커 컨테이너 이미지 저장소로 컨테이너 이미지를 손쉽게 저장, 관리 및 배포할 수 있는 네이버 클라우드 플랫폼의 서비스입니다.
Container Registry 서비스에서는 레지스트리와 도커 컨테이너 이미지 관리 기능에 대한 API를 RESTful 형태로 제공합니다.
"""

from typing import Dict, List, Optional
from ncp_api.base import BaseNCPAPI


class ContainerAPI(BaseNCPAPI):
    """
    컨테이너 리소스 API 클래스
    
    컨테이너 인스턴스 및 관련 정보를 조회합니다.
    """
    
    ENDPOINT_KEY = "containerregistry"
    
    """
    ================================================================
    컨테이너 레지스트리 관련 API
    ================================================================
    """
    def get_registry_list(
        self,
        page: Optional[int] = None,
        page_size: Optional[int] = None
        
    ) -> Dict:
        """
        컨테이너 레지스트리 목록을 조회합니다.
        
        Args:
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
        
        Returns:
            Dict: 컨테이너 레지스트리 목록 응답 데이터
        """
        params = {}

        if page is not None:
            params['page'] = page
        if page_size is not None:
            params['pagesize'] = page_size

        return self.client.get('/repositories', params=params)
    """
    ================================================================
    컨테이너 이미지 관련 API
    ================================================================
    """
    def get_image_list(
        self,
        registry_id: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None
    ) -> Dict:
        """
        컨테이너 이미지 목록을 조회합니다.
        
        Args:
            registry_id: 레지스트리 ID

        Returns:
            Dict: 컨테이너 이미지 목록 응답 데이터
        """
        params = {}

        if page is not None:
            params['page'] = page
        if page_size is not None:
            params['pagesize'] = page_size

        return self.client.get(f'/repositories/{registry_id}', params=params)

    def get_image_detail(
        self,
        registry_id: str,
        image_name: str
    ) -> Dict:
        """
        컨테이너 이미지 상세 정보를 조회합니다.
        
        Args:
            registry_id: 레지스트리 ID,
            image_name: 이미지 이름

        Returns:
            Dict: 컨테이너 이미지 상세 정보 응답 데이터
        """
        params = {}
        return self.client.get(f'/repositories/{registry_id}/{image_name}', params=params)

    def get_image_tag(
        self,
        registry_id: str,
        image_name: str,
        page: Optional[int] = None,
        page_size: Optional[int] = None
        ) -> Dict:
        """
        컨테이너 이미지 태그 목록을 조회합니다.
        
        Args:
            registry_id: 레지스트리 ID,
            image_name: 이미지 이름
        Returns:
            Dict: 컨테이너 이미지 태그 목록 응답 데이터
        """
        params = {}
        if page is not None:
            params['page'] = page
        if page_size is not None:
            params['pagesize'] = page_size

        return self.client.get(f'/repositories/{registry_id}/{image_name}/tags', params=params)

    def get_image_tag_detail(
        self,
        registry_id: str,
        image_name: str,
        reference: str
    ) -> Dict:
        """
        컨테이너 이미지 태그 상세 정보를 조회합니다.

        Args:
            registry_id: 레지스트리 ID,
            image_name: 이미지 이름름,
            reference: 태그 이름
        """
        params = {}
        return self.client.get(f'/repositories/{registry_id}/{image_name}/tags/{reference}', params=params)
