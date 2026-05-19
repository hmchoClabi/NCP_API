"""
서버 리소스 API 모듈

서버 인스턴스 및 관련 정보를 조회하는 API 모듈입니다.
"""

from typing import Dict, List, Optional
from utils.common_rest import NCPBaseClient
from ncp_api.base import BaseNCPAPI


class VServerAPI(BaseNCPAPI):
    """
    서버 리소스 API 클래스
    
    서버 인스턴스 및 관련 정보를 조회합니다.
    """
    """
    ================================================================
    서버 인스턴스 관련 API
    ================================================================
    """
    def get_server_instance_list(
        self,
        region_code: Optional[str] = None,
        vpc_no: Optional[str] = None,
        server_instanece_no_list: Optional[List[str]] = None,
        server_name: Optional[str] = None,
        server_instance_status_code: Optional[str] = None,
        base_block_storage_disk_type_code: Optional[str] = None,
        base_block_storage_disk_detail_type_code: Optional[str] = None,
        ip: Optional[str] = None,
        placement_group_no_list: Optional[List[str]] = None,
        hypervisor_type_code_list: Optional[List[str]] = None,
        fabric_cluster_pool_no: Optional[str] = None,
        fabric_cluster_no: Optional[str] = None,
        fabric_cluster_mode: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        sorted_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
        
    ) -> Dict:
        """
        서버 인스턴스 목록을 조회합니다.
        
        Args:
            str region_code: 리전 코드(선택사항)
            str vpc_NO : VPC 번호(선택사항)
            str server_name : 서버 이름(선택사항)
            str server_instance_status_code : 서버 인스턴스 상태 코드(선택사항) (INIT, CREAT,RUN, NSTOP)
            str base_Block_Storage_Disk_Type_code : 블록 스토리지 디스크 타입 코드(선택사항) (NET)
            str base_Block_Storage_Disk_Detail_Type_Code : 블록 스토리지 디스크 상세 타입 코드(선택사항) (SSD, HDD)
            str ip_address : IP 주소(선택사항)(공인/사설)
            str placement_group_no_list : 플래이스먼트 그룹 번호 리스트(선택사항)
            str hypervisor_type_code_list : 하이퍼바이저 타입 코드 리스트(선택사항) (XEN, KVM)
            str fabric_cluster_pool_no : 패브릭 클러스터 풀 번호(선택사항)
            str fabric_cluster_no : 패브릭 클러스터 번호(선택사항)
            str fabric_cluster_mode : 패브릭 클러스터 모드(선택사항) (Fabric Cluster 모드로 필터링 SINGLE | CLUSTER    SINGLE: Fabric Cluster에 포함되지 않은 서버 CLUSTER: Fabric Cluster에 포함된 서버)
            int page_no: 페이지 번호(선택사항)
            int page_size: 페이지당 항목 수(선택사항)
            str sorted_by: 정렬 기준(선택사항) (예: serverName | serverInstanceNo | serverName: 서버 이름 | serverInstanceNo: 서버 인스턴스 번호)
            str sort_order: 정렬 순서(선택사항) (ASC, DESC)
            str responseFormatType: 응답 형식(선택사항) (json)        
        Returns:
            Dict: 서버 인스턴스 목록 응답
        """
        params = {'responseFormatType': responseFormatType}  # JSON 형식 명시
        if region_code is not None:
            params['regionCode'] = region_code
        if vpc_no is not None:
            params['vpcNo'] = vpc_no
        if server_instanece_no_list is not None:
            for idx, server_instance_no in enumerate(server_instanece_no_list, start=1):
                params[f'serverInstanceNoList.{idx}'] = server_instance_no
        if server_name is not None:
            params['serverName'] = server_name
        if server_instance_status_code is not None:
            params['serverInstanceStatusCode'] = server_instance_status_code
        if base_block_storage_disk_type_code is not None:
            params['baseBlockStorageDiskTypeCode'] = base_block_storage_disk_type_code
        if base_block_storage_disk_detail_type_code is not None:
            params['baseBlockStorageDiskDetailTypeCode'] = base_block_storage_disk_detail_type_code
        if ip is not None:
            params['ip'] = ip
        if placement_group_no_list is not None:
            for idx, placement_group_no in enumerate(placement_group_no_list, start=1):
                params[f'placementGroupNoList.{idx}'] = placement_group_no
        if hypervisor_type_code_list is not None:
            for idx, hypervisor_type_code in enumerate(hypervisor_type_code_list, start=1):
                params[f'hypervisorTypeCodeList.{idx}'] = hypervisor_type_code
        if fabric_cluster_pool_no is not None:
            params['fabricClusterPoolNo'] = fabric_cluster_pool_no
        if fabric_cluster_no is not None:
            params['fabricClusterNo'] = fabric_cluster_no
        if fabric_cluster_mode is not None:
            params['fabricClusterMode'] = fabric_cluster_mode
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if sorted_by is not None:
            params['sortBy'] = sorted_by
        if sort_order is not None:
            params['sortOrder'] = sort_order
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType  # JSON 형식 명시
        
        return self.get('/vserver/v2/getServerInstanceList', params=params)
    
    def get_server_instance_detail(
        self,
        server_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        서버 인스턴스 상세 정보를 조회합니다.
        
        Args:
            server_instance_no: 서버 인스턴스 번호
            region_code: 리전 코드(선택사항)
        
        Returns:
            Dict: 서버 인스턴스 상세 정보 응답
        """
        params = {
            'serverInstanceNo': server_instance_no
            
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType  # JSON 형식 명시
        
        return self.get('/vserver/v2/getServerInstanceDetail', params=params)
    
    
    """
    ================================================================
    인증키 관련련 API
    ================================================================
    """
    def get_root_password(
        self, 
        server_instance_no: str,
        private_key: str,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        params = {
            'serverInstanceNo': server_instance_no,
            'privateKey': private_key
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType  # JSON 형식 명시

        return self.get('/vserver/v2/getRootPassword', params=params)
    
    def get_root_password_server_instance_list(
        self,
        root_password_server_instance_list_server_instance_no_list: List[str],
        root_password_server_instance_list_private_key_list: List[str],
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:

        if len(root_password_server_instance_list_server_instance_no_list) != len(root_password_server_instance_list_private_key_list):
            raise ValueError("server_instance_no_list와 private_key_list 길이가 같아야 합니다.")

        params = {}

        for idx, (server_instance_no, private_key) in enumerate(
            zip(
                root_password_server_instance_list_server_instance_no_list,
                root_password_server_instance_list_private_key_list
            ),
            start=1
        ):
            params[f'rootPasswordServerInstanceList.{idx}.serverInstanceNo'] = server_instance_no
            params[f'rootPasswordServerInstanceList.{idx}.privateKey'] = private_key

        if region_code is not None:
            params['regionCode'] = region_code

        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.post('/vserver/v2/getRootPasswordServerInstanceList', params=params)

    """
    ================================================================
    서버 이미지 관련 API
    ================================================================
    """    
    def get_server_image_list(
        self,
        region_code: Optional[str] = None,
        server_image_no_list: Optional[List[str]] = None,
        server_image_name: Optional[str] = None,
        server_image_status_code: Optional[str] = None,
        server_image_type_code_list: Optional[List[str]] = None,
        hypervisor_type_code_list: Optional[List[str]] = None,
        os_type_code_list: Optional[List[str]] = None,
        platform_category_code_list: Optional[List[str]] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        sorting_order: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        서버 이미지 목록을 조회합니다.
        
        Args:
            region_code: 리전 코드(선택사항)
            serverImageNoList.N: 서버 이미지 번호 리스트(선택사항)
            serverImageName: 서버 이미지 이름(선택사항)
            serverImageStatusCode: 서버 이미지 상태 코드(선택사항) (INIT, CREAT, CREFL)
            serverImageTypeCodeList.N: 서버 이미지 타입 코드 리스트(선택사항) (SELF, NCP)
            hypervisorTypeCodeList.N: 하이퍼바이저 타입 코드 리스트(선택사항) (XEN, KVM)
            osTypeCodeList.N: OS 타입 코드 리스트(선택사항) (CENTOS, UBUNTU, WINDOWS, ROCKY, NAVIX)
            platformCategoryCodeList.N: 플랫폼 타입 카테고리 코드 리스트(선택사항) (OS, APP, DBMS, GPU)
            pageNO : 페이지
            pageSize : 페이지 사이즈
            sortingOrder : 정렬 숫 ASC, DESC
            
        
        Returns:
            Dict: 서버 이미지 리스트 응답
        """
        params = {}
        if region_code is not None:
            params['regionCode'] = region_code
        if server_image_no_list is not None:
            for idx, server_image_no in enumerate(server_image_no_list, start=1):
                params[f'serverImageNoList.{idx}'] = server_image_no
        if server_image_name is not None:
            params['serverImageName'] = server_image_name
        if server_image_status_code is not None:
            params['serverImageStatusCode'] = server_image_status_code
        if server_image_type_code_list is not None:
            for idx, server_image_type_code in enumerate(server_image_type_code_list, start=1):
                params[f'serverImageTypeCodeList.{idx}'] = server_image_type_code
        if hypervisor_type_code_list is not None:
            for idx, hypervisor_type_code in enumerate(hypervisor_type_code_list, start=1):
                params[f'hypervisorTypeCodeList.{idx}'] = hypervisor_type_code
        if os_type_code_list is not None:
            for idx, os_type_code in enumerate(os_type_code_list, start=1):
                params[f'osTypeCodeList.{idx}'] = os_type_code
        if platform_category_code_list is not None:
            for idx, platform_type_category_code in enumerate(platform_category_code_list, start=1):
                params[f'platformCategoryCodeList.{idx}'] = platform_type_category_code
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if sorting_order is not None:
            params['sortingOrder'] = sorting_order
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/vserver/v2/getServerImageList', params=params)
    
    def server_image_detail(
        self,
        server_image_no: str,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        서버 이미지 상세 정보를 조회합니다.
        
        Args:
            server_image_no: 서버 이미지 번호
            region_code: 리전 코드(선택사항)
        
        Returns:
            Dict: 서버 이미지 상세 정보 응답
        """
        params = {
            'serverImageNo': server_image_no
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:  # JSON 형식 명시
            params['responseFormatType'] = responseFormatType
        
        return self.get('/vserver/v2/getServerImageDetail', params=params)
    
    def get_member_server_instance_list(
        self,
        region_code: Optional[str] = None,
        member_server_image_instance_no_list: Optional[List[str]] = None,
        member_server_image_name: Optional[str] = None,
        member_server_image_instance_status_code: Optional[str] = None,
        platform_type_code_list: Optional[List[str]] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        sorted_by: Optional[str] = None,
        sorting_order: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        내 서버 이미지 인스턴스 목록을 조회합니다. KVM기반은 지원하지 않습니다.

        Args:
            region_code: 리전 코드(선택사항)
            member_server_instance_no_list: 내 서버 이미지 인스턴스 번호 리스트(선택사항)
            member_server_image_name: 내 서버 이미지 이름(선택사항)
            member_server_image_instance_status_code: 내 서버 이미지 인스턴스 상태 코드(선택사항) (INIT, CREAT, CREFL)
            platform_type_code_list: 플랫폼 타입 코드 리스트(선택사항) (LNX32, LNX64, WIN32, WIN64, UBD64, UBS32)
            page_no: 페이지 
            page_size: 페이지 사이즈
            sorted_by: 정렬기준
            sorting_order: 정렬 방식 ASC, DESC
            responseFormatType : json, xml
        
        
        Returns:
            내 서버 이미지 인스턴스 목록을 조회합니다.
        """
        params = {}
        if region_code is not None:
            params['regionCode'] = region_code
        if member_server_image_instance_no_list is not None:
            for idx, member_server_image_instance_no in enumerate(member_server_image_instance_no_list, start=1):
                params[f'memberServerImageInstanceNoList.{idx}'] = member_server_image_instance_no
        if member_server_image_name is not None:
            params['memberServerImageName'] = member_server_image_name
        if member_server_image_instance_status_code is not None:
            params['memberServerImageInstanceStatusCode'] = member_server_image_instance_status_code
        if platform_type_code_list is not None:
            for idx, platform_type_code in enumerate(platform_type_code_list, start=1):
                params[f'platformTypeCodeList.{idx}'] = platform_type_code
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if sorted_by is not None:
            params['sortBy'] = sorted_by
        if sorting_order is not None:
            params['sortingOrder'] = sorting_order
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
        
        return self.get('/vserver/v2/getMemberServerImageInstanceList', params=params)

    def get_member_server_instance_detail(
        self,
        member_server_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        내 서버 이미지 인스턴스 상세 정보를 조회합니다. KVM기반은 지원하지 않습니다.
        
        Args:
            member_server_instance_no: 내 서버 이미지 인스턴스 번호
            region_code: 리전 코드(선택사항)
        
        Returns:
            Dict: 내 서버 이미지 인스턴스 상세 정보 응답
        """
        params = {
            'memberServerInstanceNo': member_server_instance_no
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        
        return self.get('/vserver/v2/getMemberServerImageInstanceDetail', params=params)
    """
    ================================================================
    블록 스토리지 관련 API
    ================================================================
    """  
        
    def get_block_storage_instance_list(
        self,
        region_code: Optional[str] = None,
        zone_code: Optional[str] = None,
        block_storage_instance_no_list: Optional[List[str]] = None,
        block_storage_instance_status_code: Optional[str] = None,
        block_storage_disk_type_code: Optional[str] = None,
        block_storage_disk_detail_type_code: Optional[str] = None,
        block_storage_size: Optional[int] = None,
        block_storage_type_code_list: Optional[List[str]] = None,
        server_instance_no: Optional[str] = None,
        block_storage_name: Optional[str] = None,
        server_name: Optional[str] = None,
        connection_info : Optional[str] = None,
        block_storage_volume_type_code_list: Optional[List[str]] = None,
        hypervisor_type_code_list: Optional[List[str]] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
    
        """
        블록 스토리지 인스턴스 목록을 조회합니다.
        서버에 마운트된 블록 스토리지를 조회할 수 있습니다.
        
        Args:
            region_code: 리전 코드(선택사항)
            zone_code: 존 코드(선택사항)
            block_storage_instance_no_list: 블록 스토리지 인스턴스 번호 리스트(선택사항)
            block_storage_instance_status_code: 블록 스토리지 인스턴스 상태 코드(선택사항) (INIT, CREAT, ATTAC)
            block_storage_disk_type_code: 블록 스토리지 디스크 타입 코드(선택사항) (NET)
            block_storage_disk_detail_type_code: 블록 스토리지 디스크 상세 타입 코드(선택사항) (SSD, HDD)
            block_storage_size: 블록 스토리지 크기(선택사항 GB)
            block_storage_type_code_list: 블록 스토리지 타입 코드 리스트(선택사항) (BASIC(기본), SVRBS(추가))
            server_instance_no: 서버 인스턴스 번호(선택사항)
            block_storage_name: 블록 스토리지 이름(선택사항) (BlockStoragename, servername, connectioninfo 중 1개만 사용)
            server_name: 서버 이름(선택사항) (BlockStoragename, servername, connectioninfo 중 1개만 사용)
            connection_info: 연결 정보(선택사항) (BlockStoragename, servername, connectioninfo 중 1개만 사용)
            block_storage_volume_type_code_list: 블록 스토리지 볼륨 타입 코드 리스트(선택사항) (HDD, SSD, FB1, CB1)
            hypervisor_type_code_list: 하이퍼바이저 타입 코드 리스트(선택사항) (XEN, KVM)
            
        
        Returns:
            Dict: 블록 스토리지 인스턴스 목록 응답
        """




        params = {'responseFormatType': responseFormatType}  # JSON 형식 명시
        if region_code is not None:
            params['regionCode'] = region_code
        if zone_code is not None:
            params['zoneCode'] = zone_code
        if block_storage_instance_no_list is not None:
            for idx, block_storage_instance_no in enumerate(block_storage_instance_no_list, start=1):
                params[f'blockStorageInstanceNoList.{idx}'] = block_storage_instance_no
        if block_storage_instance_status_code is not None:
            params['blockStorageInstanceStatusCode'] = block_storage_instance_status_code
        if block_storage_disk_type_code is not None:
            params['blockStorageDiskTypeCode'] = block_storage_disk_type_code
        if block_storage_disk_detail_type_code is not None:
            params['blockStorageDiskDetailTypeCode'] = block_storage_disk_detail_type_code
        if block_storage_size is not None:
            params['blockStorageSize'] = block_storage_size
        if block_storage_type_code_list is not None:
            for idx, block_storage_type_code in enumerate(block_storage_type_code_list, start=1):
                params[f'blockStorageTypeCodeList.{idx}'] = block_storage_type_code
        if server_instance_no is not None:
            params['serverInstanceNo'] = server_instance_no
        if block_storage_name is not None:
            params['blockStorageName'] = block_storage_name
        if server_name is not None:
            params['serverName'] = server_name
        if connection_info is not None:
            params['connectionInfo'] = connection_info
        if block_storage_volume_type_code_list is not None:
            for idx, block_storage_volume_type_code in enumerate(block_storage_volume_type_code_list, start=1):
                params[f'blockStorageVolumeTypeCodeList.{idx}'] = block_storage_volume_type_code
        if hypervisor_type_code_list:
            for idx, hypervisor_type_code in enumerate(hypervisor_type_code_list, start=1):
                params[f'hypervisorTypeCodeList.{idx}'] = hypervisor_type_code
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
        
        
        
                   
        return self.get('/vserver/v2/getBlockStorageInstanceList', params=params)
    
    
    
    def get_block_storage_instance_detail(
        self,
        block_storage_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        블록 스토리지 인스턴스 상세 정보를 조회합니다.
        
        Args:
            block_storage_instance_no: 블록 스토리지 인스턴스 번호
            region_code: 리전 코드
        
        Returns:
            Dict: 블록 스토리지 인스턴스 상세 정보 응답
        """
        params = {
            'blockStorageInstanceNo': block_storage_instance_no
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:   # JSON 형식 명시
            params['responseFormatType'] = responseFormatType
        
        return self.get('/vserver/v2/getBlockStorageInstanceDetail', params=params)
    





    def getBlockStorageVolumeTypeList(
        self,
        region_code: Optional[str],
        zone_code: Optional[str],
        block_storage_volume_type_code_list: Optional[list[str]],
        hypervisor_type_code_list: Optional[list[str]],
        server_spec_code: Optional[str],
        is_base_storage_available: Optional[str],
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        사용 가능한 블록 스토리지 볼륨 타입 코드 목록을 조회합니다.
        
        Args:
            block_storage_instance_no: 블록 스토리지 인스턴스 번호
            region_code: 리전 코드
            zone_code: 존 코드
            block_storage_volume_type_code_list.N: 블록 스토리지 볼륨 타입 코드 목록
            hypervisor_type_code_list.N: 하이퍼바이저 타입 코드 목록
            server_spec_code: 기본 스토리지 가능 여부로 필터링
            is_base_storage_available: 기본 스토리지 가능 여부로
            responseFormatType: 응답 타입
        
        Returns:
            Dict: 블록 스토리지 볼륨 타입 응답
        """
        params = {}
        if region_code is not None:
            params['regionCode'] = region_code
        if zone_code is not None:
            params['zoneCode'] = zone_code

        if block_storage_volume_type_code_list is not None:
            for idx, block_storage_volume_type_code in enumerate(block_storage_volume_type_code_list, start=1):
                params[f'blockStorageVolumeTypeCodeList.{idx}'] = block_storage_volume_type_code


        if hypervisor_type_code_list is not None:
            for idx, hypervisor_type_code in enumerate(hypervisor_type_code_list, start=1):
                params[f'hypervisorTypeCodeList.{idx}'] = hypervisor_type_code
        
        if server_spec_code is not None:
            params['serverSpecCode'] = server_spec_code
        if is_base_storage_available is not None:
            params['isBaseStorageAvailable'] = is_base_storage_available
        if responseFormatType is not None:   # JSON 형식 명시
            params['responseFormatType'] = responseFormatType
        
        return self.get('/vserver/v2/getBlockStorageVolumeTypeList', params=params)
    


    """
    ================================================================
    스냅샷 관련 API
    ================================================================
    """  
    def get_block_storage_snapshot_instance_list(
        self,
        region_code: Optional[str] = None,
        block_storage_snapshot_instance_no_list: Optional[List[str]] = None,
        block_storage_snapshot_name: Optional[str] = None,
        block_storage_snapshot_instance_status_code: Optional[str] = None,
        original_block_storage_instance_no_list: Optional[List[str]] = None,
        block_storage_snapshot_volume_size: Optional[int] = None,
        is_encrypted_original_block_storage_volume: Optional[bool] = None,
        hypervisor_type_code_list: Optional[List[str]] = None,
        is_bootable: Optional[bool] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        sorted_by: Optional[str] = None,
        sorting_order: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
    
        """
        블록 스토리지 스냅샷 인스턴스 목록을 조회합니다.

        Args:
            region_code: 리전 코드(선택사항)
            block_storage_snapshot_instance_no_list: 블록 스토리지 스냅샷 인스턴스 번호 리스트(선택사항)
            block_storage_snapshot_name: 블록 스토리지 스냅샷 이름(선택사항)
            block_storage_snapshot_instance_status_code: 블록 스토리지 스냅샷 인스턴스 상태 코드(선택사항) (INIT, CREAT)
            original_block_storage_instance_no_list: 원본 블록 스토리지 인스턴스 번호 리스트(선택사항)
            block_storage_snapshot_volume_size: 블록 스토리지 스냅샷 볼륨 크기(선택사항 GB)
            is_encrypted_original_block_storage_volume: 원본 블록 스토리지 볼륨 암호화 여부(선택사항) (true, false)
            hypervisor_type_code_list: 하이퍼바이저 타입 코드 리스트(선택사항) (XEN, KVM)
            is_bootable: 부팅 가능 여부(선택사항) (true, false)

        Returns:
            Dict: 블록 스토리지 스냅샷 인스턴스 목록 응답
        """
        
        params = {}  
        if region_code is not None:
            params['regionCode'] = region_code
        if block_storage_snapshot_instance_no_list is not None:
            for idx, block_storage_snapshot_instance_no in enumerate(block_storage_snapshot_instance_no_list, start=1):
                params[f'blockStorageSnapshotInstanceNoList.{idx}'] = block_storage_snapshot_instance_no


        if block_storage_snapshot_name is not None:
            params['blockStorageSnapshotName'] = block_storage_snapshot_name
        if block_storage_snapshot_instance_status_code is not None:
            params['blockStorageSnapshotInstanceStatusCode'] = block_storage_snapshot_instance_status_code
        if original_block_storage_instance_no_list is not None:
            for idx, original_block_storage_instance_no in enumerate(original_block_storage_instance_no_list, start=1):
                params[f'originalBlockStorageInstanceNoList.{idx}'] = original_block_storage_instance_no

        if block_storage_snapshot_volume_size is not None:
            params['blockStorageSnapshotVolumeSize'] = block_storage_snapshot_volume_size
        if is_encrypted_original_block_storage_volume is not None:
            params['isEncryptedOriginalBlockStorageVolume'] = str(is_encrypted_original_block_storage_volume).lower()
        if hypervisor_type_code_list is not None:
            for idx, hypervisor_type_code in enumerate(hypervisor_type_code_list, start=1):
                params[f'hypervisorTypeCodeList.{idx}'] = hypervisor_type_code

        if is_bootable is not None:
            params['isBootable'] = str(is_bootable).lower()

        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if sorted_by is not None:
            params['sortedBy'] = sorted_by
        if sorting_order is not None:
            params['sortingOrder'] = sorting_order
        
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
        
        return self.get('/vserver/v2/getBlockStorageSnapshotInstanceList', params=params)

    def get_block_storage_snapshot_instance_detail(
        self,
        block_storage_snapshot_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        블록 스토리지 스냅샷 인스턴스 상세 정보를 조회합니다.
        
        Args:
            block_storage_snapshot_instance_no: 블록 스토리지 스냅샷 인스턴스 번호
            region_code: 리전 코드(선택사항)
        
        Returns:
            Dict: 블록 스토리지 스냅샷 인스턴스 상세 정보 응답
        """
        params = {
            'blockStorageSnapshotInstanceNo': block_storage_snapshot_instance_no
        }
        if region_code is not None:
            params['regionCode'] = region_code
        
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType


        return self.get('/vserver/v2/getBlockStorageSnapshotInstanceDetail', params=params)
    
    """
    ================================================================
    퍼블릭 IP 관련 API
    ================================================================
    """
    def get_public_ip_instance_list(
        self,
        region_code: Optional[str] = None,
        public_ip_instance_no_list: Optional[List[str]] = None,
        public_ip : Optional[str] = None,
        private_ip : Optional[str] =None,
        is_associated: Optional[bool] = None,
        server_name: Optional[str] = None,
        public_ip_instance_status_code: Optional[str] = None,
        page_no:  Optional[str] = None,
        page_size:  Optional[str] = None,
        vpc_no: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
        
    ) -> Dict:
        """
        퍼블릭 IP 인스턴스 목록을 조회합니다.
        
        Args:
            region_code: 리전 코드(선택사항)
            public_ip_instance_no_list: 퍼블릭 IP 인스턴스 번호 리스트(선택사항)
            public_ip: 퍼블릭 IP 주소(선택사항)
            private_ip: 프라이빗 IP 주소(선택사항
            is_associated: 할당 여부(선택사항) (true, false)
            server_name: 할당된 서버 이름(선택사항)
            public_ip_instance_status_code: 퍼블릭 IP 인스턴스 상태 코드(선택사항) (INIT, SET, RUN, TERMTING)
            vpc_no: VPC 번호(선택사항)

        Returns:
            Dict: 퍼블릭 IP 인스턴스 목록 응답
        """
        params = {}      
        if region_code is not None:
            params['regionCode'] = region_code
        if public_ip_instance_no_list is not None:
            for idx, public_ip_instance_no in enumerate(public_ip_instance_no_list, start=1):
                params[f'publicIpInstanceNoList.{idx}'] = public_ip_instance_no
        if public_ip is not None:
            params['publicIp'] = public_ip
        if private_ip is not None:
            params['privateIp'] = private_ip
        if is_associated is not None:
            params['isAssociated'] = str(is_associated).lower()
        if server_name is not None:
            params['serverName'] = server_name
        if public_ip_instance_status_code is not None:
            params['publicIpInstanceStatusCode'] = public_ip_instance_status_code
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if vpc_no is not None:
            params['vpcNo'] = vpc_no
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/vserver/v2/getPublicIpInstanceList', params=params)


    def get_public_ip_instance_detail(
            self,
            public_ip_instance_no: str,
            region_code: Optional[str] = None,
            responseFormatType: Optional[str] = 'json'
    ) -> Dict:
            
        """    
        퍼블릭 IP 인스턴스 상세 정보를 조회합니다.
            
        Args:
            public_ip_instance_no: 퍼블릭 IP 인스턴스 번호
            region_code: 리전 코드(선택사항)
            
        Returns:
            Dict: 퍼블릭 IP 인스턴스 상세 정보 응답
        """

        params = {
                'publicIpInstanceNo': public_ip_instance_no
        }

        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/vserver/v2/getPublicIpInstanceDetail', params=params)

    def get_public_ip_target_server_instance_list(
        self,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        퍼블릭 IP 대상 서버 인스턴스 목록을 조회합니다.
            Args:
                region_code: 리전 코드(선택사항)
            Returns:
                Dict: 퍼블릭 IP 대상 서버 인스턴스 목록 응답
        """
        params = {}
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType    

        return self.get('/vserver/v2/getPublicIpTargetServerInstanceList', params=params)
    
    """
    ===============================================================
    INIT 스크립트 관련 API
    ================================================================
    """
    def get_init_script_list (
        self,
        region_code: Optional[str] = None,
        init_script_no_list: Optional[list[str]]= None,
        init_script_name: Optional[str] = None,
        os_type_code: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        sorted_by: Optional[str] = None,
        sorting_order: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        초기화 스크립트 목록을 조회합니다.
            Args:
                region_code: 리전코드
                init_script_no_list: 초기화 스크립트 번호 목록
                init_script_name: 초기화 스크립트 이름으로 필터링
                os_type_code: 운영 체제 타입 코드로 필터링 LNX WND
                page_no: 페이지
                page_size: 페이지 사이즈
                sorted_by: 정렬 기준
                sorting_order: 정렬 순서 ASC DESC
                responseFormatType: Optional[str] = 'json'
            Returns:
                Dict: 초기화 스크립트 목록
        """
        params = {}
        if region_code is not None:
            params['regionCode'] = region_code

        if init_script_no_list is not None:
            for idx, init_script_no in enumerate(init_script_no_list, start=1):
                params[f'initScriptNoList.{idx}'] = init_script_no

        if init_script_name is not None:
            params['initScriptName'] = init_script_name
        if os_type_code is not None:
            params['osTypeCode'] = os_type_code
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if sorted_by is not None:
            params['sortedBy'] = sorted_by
        if sorting_order is not None:
            params['sortingOrder'] = sorting_order
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType    

        return self.get('/vserver/v2/getInitScriptList', params=params)
    

    def get_init_script_detail (
        self,
        region_code: Optional[str] = None,
        init_script_no: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        초기화 스크립트의 상세 정보를 조회합니다.
            Args:
                region_code: 리전코드
                init_script_no: 초기화 스크립트 번호
                responseFormatType: Optional[str] = 'json'
            Returns:
                Dict: 초기화 스크립트 상세
        """
        params = {}
        if region_code is not None:
            params['regionCode'] = region_code

        if init_script_no is not None:
            params['initScriptNo'] = init_script_no
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType    

        return self.get('/vserver/v2/getInitScriptDetail', params=params)
            
    """
    ===============================================================
    서버 인터페이스 관련 API
    ================================================================
    """
    def get_network_interface_instance_list(
        self,
        region_code: Optional[str] = None,
        sub_name : Optional[str] = None,
        network_interface_instance_no_list: Optional[List[str]] = None,
        network_interface_name: Optional[str] = None,
        network_interface_instance_status_code: Optional[str] = None,
        ip: Optional[str] = None,
        secondary_ip_list: Optional[List[str]] = None,
        instance_no: Optional[int] = None,
        is_default: Optional[bool] = None,
        device_name: Optional[str] = None,
        server_name:  Optional[str] = None,
        page_no:  Optional[int] = None, 
        page_size:  Optional[int] = None,  
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        네트워크 인터페이스 인스턴스 목록을 조회합니다.
        
        Args:
            region_code: 리전 코드(선택사항)
            sub_name: 서브넷 이름(선택사항)
            network_interface_instance_no_list: 네트워크 인터페이스 인스턴스 번호 리스트(선택사항)
            network_interface_name: 네트워크 인터페이스 이름(선택사항)
            network_interface_instance_status_code: 네트워크 인터페이스 인스턴스 상태 코드(선택사항) (SET, UNSET, USED, NOTUSED)
            ip_address: IP 주소(선택사항)
            secondary_ip_list: 세컨더리 IP 리스트(선택사항)
            instance_no: 인스턴스 번호(선택사항)
            is_default: 기본 인터페이스 여부(선택사항) (true, false)
            device_name: 디바이스 이름(선택사항) (eth0, eth1, eth2)
            server_name: 서버 이름(선택사항)

        Returns:
            Dict: 네트워크 인터페이스 인스턴스 목록 응답
        """
        params = {}      
        if region_code is not None:
            params['regionCode'] = region_code
        if sub_name is not None:
            params['subName'] = sub_name
        if network_interface_instance_no_list is not None:
            for idx, network_interface_instance_no in enumerate(network_interface_instance_no_list, start=1):
                params[f'networkInterfaceNoList.{idx}'] = network_interface_instance_no
        if network_interface_name is not None:
            params['networkInterfaceName'] = network_interface_name
        if network_interface_instance_status_code is not None:
            params['networkInterfaceInstanceStatusCode'] = network_interface_instance_status_code
        if ip is not None:
            params['ipAddress'] = ip
        if secondary_ip_list is not None:
            for idx, secondary_ip in enumerate(secondary_ip_list, start=1):
                params[f'secondaryIpList.{idx}'] = secondary_ip
        if instance_no is not None:
            params['instanceNo'] = instance_no
        if is_default is not None:
            params['isDefault'] = str(is_default).lower()
        if device_name is not None:
            params['deviceName'] = device_name
        if server_name is not None:
            params['serverName'] = server_name
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType    
        
        return self.get('/vserver/v2/getNetworkInterfaceList', params=params)
    
    def get_network_interface_instance_detail(
        self,
        network_interface_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        네트워크 인터페이스 인스턴스 상세 정보를 조회합니다.
        
        Args:
            network_interface_instance_no: 네트워크 인터페이스 인스턴스 번호
            region_code: 리전 코드(선택사항)
        
        Returns:
            Dict: 네트워크 인터페이스 인스턴스 상세 정보 응답
        """
        params = {
            'networkInterfaceInstanceNo': network_interface_instance_no
        }
        if region_code:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType    
        
        return self.get('/vserver/v2/getNetworkInterfaceDetail', params=params)  
    
    def get_flow_log_configuration_list(
        self,
        region_code: Optional[str] = None,
        network_interface_no_list: Optional[List[str]] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        플로우 로그 구성 목록을 조회합니다.
        
        Args:
            region_code: 리전 코드(선택사항)
            network_interface_no_list: 네트워크 인터페이스 번호 리스트(선택사항)
        
        Returns:
            Dict: 플로우 로그 구성 목록 응답
        """
        params = {}
        if region_code:
            params['regionCode'] = region_code
        if network_interface_no_list:
            for idx, network_interface_no in enumerate(network_interface_no_list, start=1):
                params[f'networkInterfaceNoList.{idx}'] = network_interface_no
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType    
        
        return self.get('/vserver/v2/getFlowLogConfigurationList', params=params)
    
    """
    ================================================================
    서버 ACG 관련 API
    ================================================================
    """
    def get_access_control_group_list(
        self,
        region_code: Optional[str] = None,
        vpc_no: Optional[str] = None,
        access_control_group_no_list: Optional[List[str]] = None,
        access_control_group_name: Optional[str] = None,
        access_control_group_status_code: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        서버 ACG 목록을 조회합니다.
        
        Args:
            region_code: 리전 코드(선택사항)
            vpc_no: VPC 번호(선택사항)
            access_control_group_no_list.N: 서버 ACG 번호 리스트(선택사항)
            access_control_group_name: 서버 ACG 이름(선택사항)
            access_control_group_status_code: 서버 ACG 상태 코드(선택사항) (INIT, SET, RUN, TERMTING)
            page_no : 페이지 번호
            page_size : 페이지 사이즈즈
        
        Returns:
            Dict: 서버 ACG 목록 응답
        """
        params = {}
        if region_code is not None:
            params['regionCode'] = region_code
        if vpc_no is not None:
            params['vpcNo'] = vpc_no
        if access_control_group_no_list is not None:
            for idx, access_control_group_no in enumerate(access_control_group_no_list, start=1):
                params[f'accessControlGroupNoList.{idx}'] = access_control_group_no
        if access_control_group_name is not None:
            params['accessControlGroupName'] = access_control_group_name
        if access_control_group_status_code is not None:
            params['accessControlGroupStatusCode'] = access_control_group_status_code
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType    
        
        return self.get('/vserver/v2/getAccessControlGroupList', params=params)
    
    def get_access_control_group_detail(
        self,
        access_control_group_no: str,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        서버 ACG 상세 정보를 조회합니다.
        
        Args:
            access_control_group_no: 서버 ACG 번호
            region_code: 리전 코드(선택사항)
        
        Returns:
            Dict: 서버 ACG 상세 정보 응답
        """
        params = {
            'accessControlGroupNo': access_control_group_no
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType    
        
        return self.get('/vserver/v2/getAccessControlGroupDetail', params=params)
    
    def get_access_control_group_rule_list(
        self,
        access_control_group_no: str,
        access_control_group_rule_type_code: Optional[str] = None,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        ACG의 규칙 목록을 조회합니다.
        
        Args:
            acess_control_group_no: 서버 ACG 번호
            access_control_group_rule_type_code: 서버 ACG 룰 타입 코드(선택사항) (INBND, OTBND)
            region_code: 리전 코드(선택사항)
            
        
        Returns:
            Dict: 서버 ACG 룰 목록 응답
        """
        params = {
            'accessControlGroupNo': access_control_group_no
            
        }
        if region_code:
            params['regionCode'] = region_code
        if access_control_group_rule_type_code:
            params['accessControlGroupRuleTypeCode'] = access_control_group_rule_type_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType    
        
        
        return self.get('/vserver/v2/getAccessControlGroupRuleList', params=params)
    
    """
    ================================================================
    Fabric Cluster API
    ================================================================
    """
    def get_fabric_cluster_list(
        self,
        region_code: Optional[str] = None,
        fabric_cluster_pool_no: Optional[str] = None,
        fabric_cluster_pool_name: Optional[str] = None,
        fabric_cluster_no_list: Optional[str] = None,
        fabric_cluster_name: Optional[str] = None,
        zone_code: Optional[str] = None,
        vpc_no: Optional[str] = None,
        server_instance_no: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        sorted_by: Optional[str] = None,
        sorting_order: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        Fabric Cluster 목록을 조회합니다.

        Args:
            str region_code: 리전코드드
            str fabric_cluster_pool_no: Fabric Cluster Pool 번호로 필터링
            str fabric_cluster_pool_name: Fabric Cluster Pool 이름으로 필터링
            str fabric_cluster_no_list: Fabric Cluster 번호 목록
            str fabric_cluster_name: Fabric Cluster 이름으로 필터링
            str zone_code: 존 코드로 필터링
            str vpc_no: VPC 번호로 필터링
            str server_instance_no: 서버 인스턴스 번호로 필터링
            int page_no: 페이지 번호
            int page_size: 페이지 사이즈
            str sorted_by: 정렬 기준 ( fabricClusterNo: Fabric Cluster 번호 | fabricClusterPoolCode: Fabric Cluster Pool 코드 | zoneCode: 존 코드)
            str sorting_order: 정렬 (AES, DESC)
            str responseFormatType (JSON, XML)
        
        """
    
        params = {}

        if region_code is not None:
            params['regionCode'] = region_code
        if fabric_cluster_pool_no is not None:
            params['fabricClusterPoolNo'] = fabric_cluster_pool_no
        if fabric_cluster_pool_name is not None:
            params['fabricClusterPoolName'] = fabric_cluster_pool_name
        if fabric_cluster_no_list is not None:
            for idx, fabric_cluster_no in enumerate(fabric_cluster_no_list, start=1):
                params[f'fabricClusterNoList.{idx}'] = fabric_cluster_no
        if fabric_cluster_name is not None:
            params['fabricClusterName'] = fabric_cluster_name
        if zone_code is not None:
            params['zoneCode'] = zone_code
        if vpc_no is not None:
            params['vpcNo'] = vpc_no
        if server_instance_no is not None:
            params['serverInstanceNo'] = server_instance_no
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if sorted_by is not None:
            params['sortedBy'] = sorted_by
        if sorting_order is not None:
            params['sortingOrder'] = sorting_order
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/vserver/v2/getFabricClusterList', params=params)


    def get_fabric_cluster_detail(
        self,
        fabric_cluster_no: str,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        Fabric Cluster 상세 정보를 조회합니다.

        Args:
            str region_code: 리전코드
            str fabric_cluster_no: Fabric Cluster 번호
            str responseFormatType:  (JSON, XML)
        
        """
    
        params = {
            'fabricClusterNo' : fabric_cluster_no
        }

        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/vserver/v2/getFabricClusterDetail', params=params)


    def get_fabric_cluster_pool_list(          
        self,
        region_code: str,
        zone_code: str,
        server_spec_code: Optional[str] = None,
        server_product_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        사용 가능한 GPU Fabric Cluster Pool을 조회합니다.
        
        Args:
            region_code: 리전 코드
            str zone_code: 존 코드
            str server_spec_code: 서버 스펙 코드(선택사항)(KVM하이퍼바이져인 경우 필수)
            str server_product_code: 서버 상품 코드(선택사항)(베어메탈인 경우 필수)
            str responseFormatType:  (JSON, XML)

        
        Returns:
            Dict: 패브릭 클러스터 풀 목록 응답
        """
        params = {
            'regionCode': region_code,
            'zoneCode': zone_code
        }
        if server_spec_code is not None:
            params['serverSpecCode'] = server_spec_code
        if server_product_code is not None:
            params['serverProductCode'] = server_product_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
        
        return self.get('/vserver/v2/getFabricClusterPoolList', params=params)



    """
    ================================================================
    Common Server Related API
    ================================================================
    """
    def get_hypervisor_type_list(
        self,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        하이퍼바이저 타입 목록을 조회합니다.
        
        Args:
            region_code: 리전 코드(선택사항)
        
        Returns:
            Dict: 하이퍼바이저 타입 목록 응답
        """
        params = {}
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
        
        return self.get('/vserver/v2/getHypervisorTypeList', params=params)  
    
    def get_raid_list(
        self,
        product_type_code: str,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        RAID 목록을 조회합니다.
        
        Args:
            product_type_code: 상품 타입 코드 (LINUX, WINNT)
        
        Returns:
            Dict: RAID 목록 응답
        """
        params = {
            'productTypeCode': product_type_code
        }

        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
                
        return self.get('/vserver/v2/getRaidList', params=params)
    
    def get_region_list(
        self,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        리전 목록을 조회합니다.

        Args: 
            responseFormatType: json, xml
        
        Returns:
            Dict: 리전 목록 응답
        """
        params = {}

        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
        
                
        return self.get('/vserver/v2/getRegionList', params=params)

    def get_server_image_product_list(
        self,
        region_code: Optional[str] = None,
        block_storage_size: Optional[int] = None,
        exclusion_product_code : Optional[str] = None,
        product_code: Optional[str] = None,
        platform_type_code_list: Optional[List[str]] = None,
        infra_resource_detail_type_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        NCP에서 제공하는 서버 이미지 상품 목록을 조회합니다.
        
        Args:
            region_code: 리전 코드(선택사항)
            block_storage_size: 블록 스토리지 크기(선택사항 GB) (50GB, 100GB)
            exclusion_product_code: 제외할 상품 코드(선택사항)
            product_code: 상품 코드(선택사항)
            platform_type_code_list: 플랫폼 타입 코드 리스트(선택사항) (LNX32, LNX64, WND32, WND64, UBD64, UBS64)
            infra_resource_detail_type_code: 인프라 자원 상세 타입 코드(선택사항) (현재 BM 조회회만 지원)
            responseFormatType: xml, json
        
        Returns:
            Dict: 서버 이미지 상품 목록 응답
        """
        params = {}
        if region_code is not None:
            params['regionCode'] = region_code
        if block_storage_size is not None:
            params['blockStorageSize'] = block_storage_size
        if exclusion_product_code is not None:
            params['exclusionProductCode'] = exclusion_product_code
        if product_code is not None:
            params['productCode'] = product_code
        if platform_type_code_list is not None:
            for idx, platform_type_code in enumerate(platform_type_code_list, start=1):
                params[f'platformTypeCodeList.{idx}'] = platform_type_code
        if infra_resource_detail_type_code is not None:
            params['infraResourceDetailTypeCode'] = infra_resource_detail_type_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
        
        
        return self.get('/vserver/v2/getServerImageProductList', params=params)
    
    def get_server_product_list(
        self,
        region_code: Optional[str] = None,
        zone_code: Optional[str] = None,
        server_image_product_code: Optional[str] = None,
        exclusion_product_code: Optional[str] = None,
        product_code: Optional[str] = None,
        generation_code: Optional[str] = None,
        member_server_image_instance_no: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        서버 스펙 상품 목록을 조회합니다.
        
        Args:
            region_code: 리전 코드(선택사항)
            zone_code: 존 코드(선택사항)
            server_image_product_code: 서버 이미지 상품 코드(선택사항)
            exclusion_product_code: 제외할 상품 코드(선택사항)
            product_code: 상품 코드(선택사항)
            generation_code: 세대 코드(선택사항) (G1, G2)
            member_server_image_instance_no: 내 서버 이미지 인스턴스 번호(선택사항)

        
        Returns:
            Dict: 서버 상품 목록 응답
        """
        params = {}
        if region_code is not None:
            params['regionCode'] = region_code
        if zone_code is not None:
            params['zoneCode'] = zone_code
        if server_image_product_code is not None:
            params['serverImageProductCode'] = server_image_product_code
        if exclusion_product_code is not None:
            params['exclusionProductCode'] = exclusion_product_code
        if product_code is not None:
            params['productCode'] = product_code
        if generation_code is not None:
            params['generationCode'] = generation_code
        if member_server_image_instance_no is not None:
            params['memberServerImageInstanceNo'] = member_server_image_instance_no
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/vserver/v2/getServerProductList', params=params)
    
    def get_server_spec_detail(
        self,
        server_spec_code: str,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        서버 스펙 상세 정보를 조회합니다.
        
        Args:
            server_spec_code: 서버 스펙 코드
            region_code: 리전 코드(선택사항)
        
        Returns:
            Dict: 서버 스펙 상세 정보 응답
        """
        params = {
            'serverSpecCode': server_spec_code            
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
        
        return self.get('/vserver/v2/getServerSpecDetail', params=params)
    
    def get_server_spec_list(
        self,
        region_code: Optional[str] = None,
        zone_code: Optional[str] = None,
        server_image_no: Optional[str] = None,
        server_spec_code_list: Optional[List[str]] = None,
        hypervisor_type_code_list: Optional[List[str]] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        서버 스펙 목록을 조회합니다.
        
        Args:
            region_code: 리전 코드(선택사항)
            zone_code: 존 코드(선택사항)
            server_image_no: 서버 이미지 번호(선택사항)
            server_spec_code_list: 서버 스펙 코드 리스트(선택사항)
            hypervisor_type_code_list: 하이퍼바이저 타입 코드 리스트(선택사항) (XEN, KVM)
        
        Returns:
            Dict: 서버 스펙 목록 응답
        """
        params = {}
        if region_code is not None:
            params['regionCode'] = region_code
        if zone_code is not None:
            params['zoneCode'] = zone_code
        if server_image_no is not None:
            params['serverImageNo'] = server_image_no
        if server_spec_code_list is not None:
            for idx, server_spec_code in enumerate(server_spec_code_list, start=1):
                params[f'serverSpecCodeList.{idx}'] = server_spec_code
        if hypervisor_type_code_list is not None:
            for idx, hypervisor_type_code in enumerate(hypervisor_type_code_list, start=1):
                params[f'hypervisorTypeCodeList.{idx}'] = hypervisor_type_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

        return self.get('/vserver/v2/getServerSpecList', params=params)
    
    def get_zone_list(
        self,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        존 목록을 조회합니다.
        
        Args:
            region_code: 리전 코드(선택사항)
        
        Returns:
            Dict: 존 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code

        return self.get('/vserver/v2/getZoneList', params=params)
    
