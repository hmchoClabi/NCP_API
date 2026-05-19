"""
쿠버네티스 리소스 API 모듈
Kubernetes 환경 제어 및 관리 기능에 대한 API를 RESTful 형태로 제공합니다.
"""
from typing import Dict, List, Optional
from utils.common_rest import NCPBaseClient
from ncp_api.base import BaseNCPAPI


class KubernetesAPI(BaseNCPAPI):
    """
    Kubernetes 리소스 API 클래스

    Kubernetes 인스턴스 및 관련 정보를 조회합니다.
    """
  
  
    """
    ================================================================
    NKS 관련 API
    ================================================================
    """
    def get_nks_cluster_list(
        self
    ) -> Dict:
        """
        NKS 클러스터 목록을 조회합니다.
        
        Args:
            none
        R
        Returns:
            Dict: NKS 클러스터 목록 응답 데이터
        """
        params = {}
        return self.get(f'/clusters', params=params)

    def get_nks_cluster_detail(
        self,
        uuid: str
    ) -> Dict:
        """
        Cluster 조회
        특정클러스터의 정보를 조회합니다.
        
        Args:
            uuid: 클러스터 UUID
        Returns:
            Dict: NKS 클러스터 상세 정보 응답 데이터
        """
        params = {}
        return self.get(f'/clusters/{uuid}', params=params)

    def get_nks_cluster_oidc(
        self,
        uuid: str
    ) -> Dict:
        """
        NKS 클러스터 OIDC 설정 정보를 조회합니다.
        
        Args:
            uuid: 클러스터 UUID
        Returns:
            Dict: NKS 클러스터 OIDC 정보 응답 데이터
        """
        params = {}
        return self.get(f'/clusters/{uuid}/oidc', params=params)

    def get_nks_cluster_ip_acl(
        self,
        uuid: str
    ) -> Dict:
        """
        클러스터에 설정한 IP ACL 정보를 조회합니다.
        
        Args:
            uuid: 클러스터 UUID
        Returns:
            Dict: NKS 클러스터 IP ACL 정보 응답 데이터
        """
        params = {}
        return self.get(f'/clusters/{uuid}/ip-acl', params=params)

    def get_nks_cluster_iam_access_list(
        self,
        uuid: str
    ) -> Dict:
        """
        특정 클러스터의 IAM 액세스 목록 정보를 조회합니다.
        
        Args:
            uuid: 클러스터 UUID
        Returns:
            Dict: NKS 클러스터 IAM 액세스 목록 정보 응답 데이터
        """
        params = {}
        return self.get(f'/clusters/{uuid}/access-entries', params=params)

    def get_nks_cluster_iam_access(
        self,
        uuid: str,
        entryUuid: str
    ) -> Dict:
        """
        특정 클러스터의 IAM 액세스 정보를 조회합니다.
        
        Args:
            uuid: 클러스터 UUID
        Returns:
            Dict: NKS 클러스터 IAM 액세스 정보 응답 데이터
        """
        params = {}
        return self.get(f'/clusters/{uuid}/access-entries/{entryUuid}', params=params)

    def get_nks_cluster_worker_node(
        self,
        uuid: str
    ) -> Dict:
        """
        NKS 클러스터 워커 노드 정보를 조회합니다.
        
        Args:
            uuid: 클러스터 UUID
        Returns:
            Dict: NKS 클러스터 워커 노드 정보 응답 데이터
        """
        params = {}
        return self.get(f'/clusters/{uuid}/nodes', params=params)

    def get_nks_cluster_nodepool_list(
        self,
        uuid: str,
        hypervisor_code: Optional[str] = None
    ) -> Dict:
        """
        NKS 클러스터 노드풀 목록 정보를 조회합니다.
        
        Args:
            uuid: 클러스터 UUID
            hypervisor_code: 하이퍼바이져 코드(xen, kvm) (선택사항)
        Returns:
            Dict: NKS 클러스터 노드풀 목록 정보 응답 데이터
        """
        params = {}
        if hypervisor_code is not None:
            params['hypervisorCode'] = hypervisor_code
        return self.get(f'/clusters/{uuid}/node-pool', params=params)

    def get_nks_kubeconfig(
        self,
        uuid: str
    ) -> Dict:
        """
        NKS 클러스터 Kubeconfig 설정 파일을 조회합니다.
        
        Args:
            uuid: 클러스터 UUID
        Returns:
            Dict: NKS 클러스터 Kubeconfig 정보 응답 데이터
        """
        params = {}
        return self.get(f'/clusters/{uuid}/kubeconfig', params=params)

    def get_nks_support_version(
        self,
        hypervisor_code: Optional[str] = None,
        is_regional_support: Optional[bool] = None
    ) -> Dict:
        """
        NKS 클러스터 지원 버전 정보를 조회합니다.
        
        Args:
            hypervisorCode: 하이퍼바이저 코드 (XEN, KVM)
        Returns:
            Dict: NKS 클러스터 지원 버전 정보 응답 데이터
        """
        params = {}
        if hypervisor_code is not None:
            params['hypervisorCode'] = hypervisor_code
        if is_regional_support is not None:
            params['isRegionalSupport'] = is_regional_support
        return self.get(f'/option/version', params=params)

    def get_nks_cluster_server_image(
        self,
        hypervisor_code: Optional[str] = None
    ) -> Dict:
        """
        NKS 클러스터 서버 이미지 정보를 조회합니다.
        
        Args:
            hypervisorCode: 하이퍼바이저 코드 (XEN, KVM)
        Returns:
            Dict: NKS 클러스터 서버 이미지 정보 응답 데이터
        """
        params = {}
        if hypervisor_code is not None:
            params['hypervisorCode'] = hypervisor_code
        return self.get(f'/option/server-image', params=params)

    def get_nks_cluster_server_spec(
        self,
        software_code: str,
        zone_code: Optional[str] = None,
        zone_no: Optional[str] = None
    ) -> Dict:
        """
        NKS 클러스터 서버 스펙 정보를 조회합니다.
        
        Args:
            software_code: 소프트웨어 코드
            zone_code: 존 코드 (선택사항)
            zone_no: 존 번호 (선택사항)
        Returns:
            Dict: NKS 클러스터 서버 스펙 정보 응답 데이터
        """
        params = {'softwareCode': software_code}
        if not zone_no and not zone_code:
            raise ValueError("zoneNo 또는 zoneCode 중 하나는 필수 입력 값입니다.")
        if zone_no is not None:
            params['zoneNo'] = zone_no
        if zone_code is not None:
            params['zoneCode'] = zone_code
        return self.get(f'/option/server-product-code', params=params)