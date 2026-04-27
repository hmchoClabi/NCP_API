"""
서버 리소스 API 모듈

서버 인스턴스 및 관련 정보를 조회하는 API 모듈입니다.
"""

from typing import Dict, List, Optional
from utils.common_rest import NCPBaseClient


class VServerAPI:
    """
    서버 리소스 API 클래스
    
    서버 인스턴스 및 관련 정보를 조회합니다.
    """
    
    def __init__(self, client: NCPBaseClient):
        """
        ServerAPI를 초기화합니다.
        
        Args:
            client: NCPBaseClient 인스턴스
        """
        self.client = client
    """
    ================================================================
    서버 인스턴스 관련 API
    ================================================================
    """
    def get_server_instance_list(
        self,
        region_code: Optional[str] = None,
        vpc_NO: Optional[str] = None,
        server_instanece_no_list: Optional[List[str]] = None,
        server_name: Optional[str] = None,
        server_instance_status_code: Optional[str] = None,
        base_block_storage_disk_type_code: Optional[str] = None,
        base_block_storage_disk_detail_type_code: Optional[str] = None,
        ip_address: Optional[str] = None,
        zone_code: Optional[str] = None,  
        responseFormatType: str = 'json'
        
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
            zone_code: 존 코드
            server_instance_no_list: 서버 인스턴스 번호 리스트
        
        Returns:
            Dict: 서버 인스턴스 목록 응답
        """
        params = {'responseFormatType': responseFormatType}  # JSON 형식 명시
        if region_code:
            params['regionCode'] = region_code
        if vpc_NO:
            params['vpcNo'] = vpc_NO
        if server_instanece_no_list:
            params['serverInstanceNoList'] = server_instanece_no_list  
        if zone_code:
            params['zoneCode'] = zone_code
        if server_name:
            params['serverName'] = server_name
        if server_instance_status_code:
            params['serverInstanceStatusCode'] = server_instance_status_code
        if base_block_storage_disk_type_code:
            params['baseBlockStorageDiskTypeCode'] = base_block_storage_disk_type_code
        if base_block_storage_disk_detail_type_code:
            params['baseBlockStorageDiskDetailTypeCode'] = base_block_storage_disk_detail_type_code
        if ip_address:
            params['ipAddress'] = ip_address
        
        
        return self.client.get('/vserver/v2/getServerInstanceList', params=params)
    
    def get_server_instance_detail(
        self,
        server_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
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
            'serverInstanceNo': server_instance_no,
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        
        return self.client.get('/vserver/v2/getServerInstanceDetail', params=params)
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
        platform_type_category_code_list: Optional[List[str]] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        서버 이미지 목록을 조회합니다.
        
        Args:
            region_code: 리전 코드(선택사항)
            serverImageNoList.N: 서버 이미지 번호 리스트(선택사항)
            serverImageName: 서버 이미지 이름(선택사항)
            serverImageStatusCode: 서버 이미지 상태 코드(선택사항) (INIT, CREAT)
            serverImageTypeCodeList.N: 서버 이미지 타입 코드 리스트(선택사항) (SELF, NCP)
            hypervisorTypeCodeList.N: 하이퍼바이저 타입 코드 리스트(선택사항) (XEN, KVM)
            osTypeCodeList.N: OS 타입 코드 리스트(선택사항) (CENTOS, UBUNTU, WINDOWS)
            platformtypeCategoryCodeList.N: 플랫폼 타입 카테고리 코드 리스트(선택사항) (OS, APP, DBMS, GPU)
            
        
        Returns:
            Dict: 서버 이미지 리스트 응답
        """
        params = {
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        if server_image_no_list:
            params['serverImageNoList'] = server_image_no_list
        if server_image_name:
            params['serverImageName'] = server_image_name
        if server_image_status_code:
            params['serverImageStatusCode'] = server_image_status_code
        if server_image_type_code_list:
            params['serverImageTypeCodeList'] = server_image_type_code_list
        if hypervisor_type_code_list:
            params['hypervisorTypeCodeList'] = hypervisor_type_code_list   
        if os_type_code_list:
            params['osTypeCodeList'] = os_type_code_list
        if platform_type_category_code_list:
            params['platformTypeCategoryCodeList'] = platform_type_category_code_list

        return self.client.get('/vserver/v2/getServerImageList', params=params)
    
    def server_image_detail(
        self,
        server_image_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
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
            'serverImageNo': server_image_no,
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        
        return self.client.get('/vserver/v2/getServerImageDetail', params=params)
    
    def get_member_server_instance_list(
        self,
        region_code: Optional[str] = None,
        member_server_instance_no_list: Optional[List[str]] = None,
        member_server_image_name: Optional[str] = None,
        member_server_image_instance_status_code: Optional[str] = None,
        platform_type_code_list: Optional[List[str]] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        내 서버 이미지 인스턴스 목록을 조회합니다. KVM기반은 지원하지 않습니다.

        Args:
            region_code: 리전 코드(선택사항)
            member_server_instance_no_list: 내 서버 이미지 인스턴스 번호 리스트(선택사항)
            member_server_image_name: 내 서버 이미지 이름(선택사항)
            member_server_image_instance_status_code: 내 서버 이미지 인스턴스 상태 코드(선택사항) (INIT, CREAT)
            platform_type_code_list: 플랫폼 타입 코드 리스트(선택사항) (LNX32, LNX64, WIN32, WIN64, UBD64, UBS32)
        
        Returns:
            Dict: 내 서버 이미지 인스턴스 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        if member_server_instance_no_list:
            params['memberServerInstanceNoList'] = member_server_instance_no_list
        if member_server_image_name:
            params['memberServerImageName'] = member_server_image_name
        if member_server_image_instance_status_code:
            params['memberServerImageInstanceStatusCode'] = member_server_image_instance_status_code
        if platform_type_code_list:
            params['platformTypeCodeList'] = platform_type_code_list
        
        return self.client.get('/vserver/v2/getMemberServerImageInstanceList', params=params)

    def get_member_server_instance_detail(
        self,
        member_server_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
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
            'memberServerInstanceNo': member_server_instance_no,
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        
        return self.client.get('/vserver/v2/getMemberServerImageInstanceDetail', params=params)
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
        responseFormatType: str = 'json'       
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
        if region_code:
            params['regionCode'] = region_code
        if zone_code:
            params['zoneCode'] = zone_code
        if block_storage_instance_no_list:
            params['blockStorageInstanceNoList'] = block_storage_instance_no_list
        if block_storage_instance_status_code:
            params['blockStorageInstanceStatusCode'] = block_storage_instance_status_code
        if block_storage_disk_type_code:
            params['blockStorageDiskTypeCode'] = block_storage_disk_type_code
        if block_storage_disk_detail_type_code:
            params['blockStorageDiskDetailTypeCode'] = block_storage_disk_detail_type_code
        if block_storage_size:
            params['blockStorageSize'] = block_storage_size
        if block_storage_type_code_list:
            params['blockStorageTypeCodeList'] = block_storage_type_code_list
        if server_instance_no:
            params['serverInstanceNo'] = server_instance_no
        if block_storage_name:
            params['blockStorageName'] = block_storage_name
        if server_name:
            params['serverName'] = server_name
        if connection_info:
            params['connectionInfo'] = connection_info
        if block_storage_volume_type_code_list:
            params['blockStorageVolumeTypeCodeList'] = block_storage_volume_type_code_list
        if hypervisor_type_code_list:
            params['hypervisorTypeCodeList'] = hypervisor_type_code_list
                   
        return self.client.get('/vserver/v2/getBlockStorageInstanceList', params=params)
    
    
    
    def get_block_storage_instance_detail(
        self,
        block_storage_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
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
            'blockStorageInstanceNo': block_storage_instance_no,
            'responseFormatType': responseFormatType   # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        
        return self.client.get('/vserver/v2/getBlockStorageInstanceDetail', params=params) 
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
        responseFormatType: str = 'json'
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
        
        params = {
            'responseFormatType': responseFormatType    # JSON 형식 명시
        }  
        if region_code:
            params['regionCode'] = region_code
        if block_storage_snapshot_instance_no_list:
            params['blockStorageSnapshotInstanceNoList'] = block_storage_snapshot_instance_no_list
        if block_storage_snapshot_name:
            params['blockStorageSnapshotName'] = block_storage_snapshot_name
        if block_storage_snapshot_instance_status_code:
            params['blockStorageSnapshotInstanceStatusCode'] = block_storage_snapshot_instance_status_code
        if original_block_storage_instance_no_list:
            params['originalBlockStorageInstanceNoList'] = original_block_storage_instance_no_list
        if block_storage_snapshot_volume_size:
            params['blockStorageSnapshotVolumeSize'] = block_storage_snapshot_volume_size
        if is_encrypted_original_block_storage_volume is not None:
            params['isEncryptedOriginalBlockStorageVolume'] = str(is_encrypted_original_block_storage_volume).lower()
        if hypervisor_type_code_list:
            params['hypervisorTypeCodeList'] = hypervisor_type_code_list
        if is_bootable is not None:
            params['isBootable'] = str(is_bootable).lower()
        
        return self.client.get('/vserver/v2/getBlockStorageSnapshotInstanceList', params=params)

    def get_block_storage_snapshot_instance_detail(
        self,
        block_storage_snapshot_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
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
            'blockStorageSnapshotInstanceNo': block_storage_snapshot_instance_no,
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        
        return self.client.get('/vserver/v2/getBlockStorageSnapshotInstanceDetail', params=params)
    
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
        vpc_no: Optional[str] = None,
        responseFormatType: str = 'json'
        
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
        params = {
            'responseFormatType': responseFormatType # JSON 형식 명시 
        }      
        if region_code:
            params['regionCode'] = region_code
        if public_ip_instance_no_list:
            params['publicIpInstanceNoList'] = public_ip_instance_no_list
        if public_ip:
            params['publicIp'] = public_ip
        if private_ip:
            params['privateIp'] = private_ip
        if is_associated is not None:
            params['isAssociated'] = str(is_associated).lower()
        if server_name:
            params['serverName'] = server_name
        if public_ip_instance_status_code:
            params['publicIpInstanceStatusCode'] = public_ip_instance_status_code
        if vpc_no:
            params['vpcNo'] = vpc_no

        return self.client.get('/vserver/v2/getPublicIpInstanceList', params=params)


    def get_public_ip_instance_detail(
            self,
            public_ip_instance_no: str,
            region_code: Optional[str] = None,
            responseFormatType: str = 'json'
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
                'publicIpInstanceNo': public_ip_instance_no,
                'responseFormatType': responseFormatType  # JSON 형식 명시
        }

        if region_code:
            params['regionCode'] = region_code

        return self.client.get('/vserver/v2/getPublicIpInstanceDetail', params=params)

    def get_public_ip_target_server_instance_list(
        self,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        퍼블릭 IP 대상 서버 인스턴스 목록을 조회합니다.
            Args:
                region_code: 리전 코드(선택사항)
            Returns:
                Dict: 퍼블릭 IP 대상 서버 인스턴스 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code

        return self.client.get('/vserver/v2/getPublicIpTargetServerInstanceList', params=params)
            
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
        responseFormatType: str = 'json'
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
        params = {
            'responseFormatType': responseFormatType # JSON 형식 명시 
        }      
        if region_code:
            params['regionCode'] = region_code
        if sub_name:
            params['subName'] = sub_name
        if network_interface_instance_no_list:
            params['networkInterfaceInstanceNoList'] = network_interface_instance_no_list
        if network_interface_name:
            params['networkInterfaceName'] = network_interface_name
        if network_interface_instance_status_code:
            params['networkInterfaceInstanceStatusCode'] = network_interface_instance_status_code
        if ip:
            params['ipAddress'] = ip
        if secondary_ip_list:
            params['secondaryIpList'] = secondary_ip_list
        if instance_no:
            params['instanceNo'] = instance_no
        if is_default is not None:
            params['isDefault'] = str(is_default).lower()
        if device_name:
            params['deviceName'] = device_name
        if server_name:
            params['serverName'] = server_name
        
        return self.client.get('/vserver/v2/getNetworkInterfaceList', params=params)
    
    def get_network_interface_instance_detail(
        self,
        network_interface_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
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
            'networkInterfaceInstanceNo': network_interface_instance_no,
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        
        return self.client.get('/vserver/v2/getNetworkInterfaceDetail', params=params)  
    
    def get_flow_log_configuration_list(
        self,
        region_code: Optional[str] = None,
        network_interface_no_list: Optional[List[str]] = None,
        reseponseFormatType: str = 'json'
    ) -> Dict:
        """
        플로우 로그 구성 목록을 조회합니다.
        
        Args:
            region_code: 리전 코드(선택사항)
            network_interface_no_list: 네트워크 인터페이스 번호 리스트(선택사항)
        
        Returns:
            Dict: 플로우 로그 구성 목록 응답
        """
        params = {
            'responseFormatType': reseponseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        if network_interface_no_list:
            params['networkInterfaceNoList'] = network_interface_no_list
        
        return self.client.get('/vserver/v2/getFlowLogConfigurationList', params=params)
    
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
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        서버 ACG 목록을 조회합니다.
        
        Args:
            region_code: 리전 코드(선택사항)
            vpc_no: VPC 번호(선택사항)
            access_control_group_no_list: 서버 ACG 번호 리스트(선택사항)
            access_control_group_name: 서버 ACG 이름(선택사항)
            access_control_group_status_code: 서버 ACG 상태 코드(선택사항) (INIT, SET, RUN, TERMTING)
        
        Returns:
            Dict: 서버 ACG 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        if vpc_no:
            params['vpcNo'] = vpc_no
        if access_control_group_no_list:
            params['accessControlGroupNoList'] = access_control_group_no_list
        if access_control_group_name:
            params['accessControlGroupName'] = access_control_group_name
        if access_control_group_status_code:
            params['accessControlGroupStatusCode'] = access_control_group_status_code
        
        return self.client.get('/vserver/v2/getAccessControlGroupList', params=params)
    
    def get_access_control_group_detail(
        self,
        access_control_group_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
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
            'accessControlGroupNo': access_control_group_no,
            'responseFormatType': responseFormatType
        }
        if region_code:
            params['regionCode'] = region_code
        
        return self.client.get('/vserver/v2/getAccessControlGroupDetail', params=params)
    
    def get_access_control_group_rule_list(
        self,
        access_control_group_no: None,
        access_control_group_rule_type_code: Optional[str] = None,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        서버 ACG 룰 목록을 조회합니다.
        
        Args:
            acess_control_group_no: 서버 ACG 번호
            access_control_group_rule_type_code: 서버 ACG 룰 타입 코드(선택사항) (INBND, OTBND)
            region_code: 리전 코드(선택사항)
            
        
        Returns:
            Dict: 서버 ACG 룰 목록 응답
        """
        params = {
            'accessControlGroupNo': access_control_group_no,
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        if access_control_group_rule_type_code:
            params['accessControlGroupRuleTypeCode'] = access_control_group_rule_type_code
        
        
        return self.client.get('/vserver/v2/getAccessControlGroupRuleList', params=params)
    
    """
    ================================================================
    Common API
    ================================================================
    """
    def get_fabric_cluster_pool_list(          
        self,
        region_code: str,
        zone_code: str,
        server_spec_code: Optional[str] = None,
        server_product_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        사용 가능한 GPU Fabric Cluster Pool을 조회합니다.
        
        Args:
            region_code: 리전 코드
            zone_code: 존 코드
            server_spec_code: 서버 스펙 코드(선택사항)(KVM하이퍼바이져인 경우 필수)
            server_product_code: 서버 상품 코드(선택사항)(베어메탈인 경우 필수)

        
        Returns:
            Dict: 패브릭 클러스터 풀 목록 응답
        """
        params = {
            'regionCode': region_code,
            'zoneCode': zone_code,
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if server_spec_code:
            params['serverSpecCode'] = server_spec_code
        if server_product_code:
            params['serverProductCode'] = server_product_code
        
        return self.client.get('/vserver/v2/getFabricClusterPoolList', params=params
    )

    def get_hypervisor_type_list(
        self,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        하이퍼바이저 타입 목록을 조회합니다.
        
        Args:
            region_code: 리전 코드(선택사항)
        
        Returns:
            Dict: 하이퍼바이저 타입 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        
        return self.client.get('/vserver/v2/getHypervisorTypeList', params=params)  
    
    def get_raid_list(
        self,
        product_type_code: str,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        RAID 목록을 조회합니다.
        
        Args:
            product_type_code: 상품 타입 코드 (LINUX, WINNT)
        
        Returns:
            Dict: RAID 목록 응답
        """
        params = {
            'productTypeCode': product_type_code,
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
                
        return self.client.get('/vserver/v2/getRaidList', params=params)
    
    def get_region_list(
        self,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        리전 목록을 조회합니다.
        
        Returns:
            Dict: 리전 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
                
        return self.client.get('/vserver/v2/getRegionList', params=params)

    def get_server_image_product_list(
        self,
        region_code: Optional[str] = None,
        block_storage_size: Optional[int] = None,
        exclusion_product_code : Optional[str] = None,
        product_code: Optional[str] = None,
        platform_type_code_list: Optional[List[str]] = None,
        infra_resource_detail_type_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        NCP에서 제공하는 서버 이미지 상품 목록을 조회합니다.
        
        Args:
            region_code: 리전 코드(선택사항)
            block_storage_size: 블록 스토리지 크기(선택사항 GB) (50GB, 100GB)
            exclusion_product_code: 제외할 상품 코드(선택사항)
            product_code: 상품 코드(선택사항)
            platform_type_code_list: 플랫폼 타입 코드 리스트(선택사항) (LNX32, LNX64, WND32, WND64, UBD64, UBS64)
            infra_resource_detail_type_code: 인프라 자원 상세 타입 코드(선택사항) (현재 BM만 지원)        
        
        Returns:
            Dict: 서버 이미지 상품 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        if block_storage_size:
            params['blockStorageSize'] = block_storage_size
        if exclusion_product_code:
            params['exclusionProductCode'] = exclusion_product_code
        if product_code:
            params['productCode'] = product_code
        if platform_type_code_list:
            params['platformTypeCodeList'] = platform_type_code_list
        if infra_resource_detail_type_code:
            params['infraResourceDetailTypeCode'] = infra_resource_detail_type_code
        
        
        return self.client.get('/vserver/v2/getServerImageProductList', params=params)
    
    def get_server_product_list(
        self,
        region_code: Optional[str] = None,
        zone_code: Optional[str] = None,
        server_image_product_code: Optional[str] = None,
        exclusion_product_code: Optional[str] = None,
        product_code: Optional[str] = None,
        generation_code: Optional[str] = None,
        member_server_image_instance_no: Optional[str] = None,
        responseFormatType: str = 'json'
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
        params = {
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        if zone_code:
            params['zoneCode'] = zone_code
        if server_image_product_code:
            params['serverImageProductCode'] = server_image_product_code
        if exclusion_product_code:
            params['exclusionProductCode'] = exclusion_product_code
        if product_code:
            params['productCode'] = product_code
        if generation_code:
            params['generationCode'] = generation_code
        if member_server_image_instance_no:
            params['memberServerImageInstanceNo'] = member_server_image_instance_no

        return self.client.get('/vserver/v2/getServerProductList', params=params)
    
    def get_server_spec_detail(
        self,
        server_spec_code: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
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
            'serverSpecCode': server_spec_code,
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        
        return self.client.get('/vserver/v2/getServerSpecDetail', params=params)
    
    def get_server_spec_list(
        self,
        region_code: Optional[str] = None,
        zone_code: Optional[str] = None,
        server_image_no: Optional[str] = None,
        server_spec_code_list: Optional[List[str]] = None,
        hypervisor_type_code_list: Optional[List[str]] = None,
        responseFormatType: str = 'json'
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
        params = {
            'responseFormatType': responseFormatType  # JSON 형식 명시
        }
        if region_code:
            params['regionCode'] = region_code
        if zone_code:
            params['zoneCode'] = zone_code
        if server_image_no:
            params['serverImageNo'] = server_image_no
        if server_spec_code_list:
            params['serverSpecCodeList'] = server_spec_code_list
        if hypervisor_type_code_list:
            params['hypervisorTypeCodeList'] = hypervisor_type_code_list

        return self.client.get('/vserver/v2/getServerSpecList', params=params)
    
    def get_zone_list(
        self,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
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

        return self.client.get('/vserver/v2/getZoneList', params=params)
    

    

    


    
