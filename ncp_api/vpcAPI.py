"""
VPC 리소스 API 모듈

VPC 인스턴스 및 관련 정보를 조회하는 API 모듈입니다.

"""

from bisect import insort_right
from typing import Dict, List, Optional
from ncp_api.base import BaseNCPAPI



class VpcAPI(BaseNCPAPI):
    """
    VPC 리소스 API 클래스

    VPC 인스턴스 및 관련 정보를 조회합니다.
    """
    ENDPOINT_KEY = "vpc"
    
    """
    ================================================================
    VPC 인스턴스 관련 API
    ================================================================
    """
    def get_vpc_list(
        self,
        region_code: Optional[str] = None,
        vpc_status_code: Optional[str] = None,
        vpc_name: Optional[str] = None,
        vpc_no_list: Optional[List[str]] = None,
        responseFormatType: str = 'json'    
    ) -> Dict:
        """
        VPC 목록을 조회합니다.

        Args:
            str region_code: 리전 코드(선택사항)
            str vpc_status_code: VPC 상태 코드(선택사항)
            str vpc_name: VPC 이름(선택사항)
            list vpc_no_list: VPC 번호 리스트(선택사항)
            str responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)

        Returns:
            Dict: VPC 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if vpc_status_code is not None:
            params['vpcStatusCode'] = vpc_status_code
        if vpc_name is not None:
            params['vpcName'] = vpc_name
        if vpc_no_list is not None:
            for idx, vpc_no in enumerate(vpc_no_list, start=1):
                params[f'vpcNoList.{idx}'] = vpc_no
        return self.client.get('/getVpcList', params=params)

    def get_vpc_detail(
        self,
        vpc_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        VPC 상세 정보를 조회합니다.

        Args:
            str vpc_no: VPC 번호
            str region_code: 리전 코드(선택사항)

        Returns:
            Dict: VPC 상세 정보 응답
        """
        params = {
            'vpcNo': vpc_no,
            'responseFormatType': responseFormatType
        }
        if region_code is not None:
            params['regionCode'] = region_code
        return self.client.get('/getVpcDetail', params=params)
    

    """
    ================================================================
    SUBNET 인스턴스 관련 API
    ================================================================
    """
    def get_subnet_list(
        self,
        region_code: Optional[str] = None,
        subnet_no_list: Optional[List[str]] = None,
        subnet_name: Optional[str] = None,
        subnet: Optional[str] = None,
        subnet_type_code: Optional[str] = None,
        usage_type_code: Optional[str] = None,
        network_acl_no: Optional[str] = None,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        subnet_status_code: Optional[str] = None,
        vpc_no: Optional[str] = None,
        zone_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        SUBNET 목록을 조회합니다.

        Args:
            str region_code: 리전 코드(선택사항)
            list subnet_no_list: SUBNET 번호 리스트(선택사항)
            str subnet_name: SUBNET 이름(선택사항)
            str subnet: SUBNET(선택사항)
            str subnet_type_code: SUBNET 타입 코드(선택사항)
            str usage_type_code: 사용 타입 코드(선택사항)
            str network_acl_no: NACL 번호(선택사항)
            int page: 페이지 번호(선택사항)
            int page_size: 페이지 크기(선택사항)
            str subnet_status_code: SUBNET 상태 코드(선택사항)
            str vpc_no: VPC 번호(선택사항)
            str zone_code: 존 코드(선택사항)

        Returns:
            Dict: SUBNET 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if subnet_no_list is not None:
            for idx, subnet_no in enumerate(subnet_no_list, start=1):
                params[f'subnetNoList.{idx}'] = subnet_no
        if subnet_name is not None:
            params['subnetName'] = subnet_name
        if subnet is not None:
            params['subnet'] = subnet
        if subnet_type_code is not None:
            params['subnetTypeCode'] = subnet_type_code
        if usage_type_code is not None:
            params['usageTypeCode'] = usage_type_code
        if network_acl_no is not None:
            params['networkAclNo'] = network_acl_no
        if page is not None:
            params['page'] = page
        if page_size is not None:
            params['pageSize'] = page_size
        if subnet_status_code is not None:
            params['subnetStatusCode'] = subnet_status_code
        if vpc_no is not None:
            params['vpcNo'] = vpc_no
        if zone_code is not None:
            params['zoneCode'] = zone_code
        return self.client.get('/getSubnetList', params=params)

    def get_subnet_detail(
        self,
        subnet_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        SUBNET 상세 정보를 조회합니다.

        Args:
            str subnet_no: SUBNET 번호
            str region_code: 리전 코드(선택사항)

        Returns:
            Dict: SUBNET 상세 정보 응답
        """
        params = {
            'subnetNo': subnet_no,
            'responseFormatType': responseFormatType
        }
        if region_code is not None:
            params['regionCode'] = region_code
        return self.client.get('/getSubnetDetail', params=params)


    """
    ================================================================
    NACL 인스턴스 관련 API
    ================================================================
    """
    
    def get_network_acl_list(
        self,
        region_code: Optional[str] = None,
        network_acl_name: Optional[str] = None,
        network_acl_status_code: Optional[str] = None,
        network_acl_no_list: Optional[List[str]] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        vpc_no: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:

        """
        사용자가 지정한 조건에 따라 Network ACL 목록을 조회합니다.
    
        args:
            str region_code: 리전 코드(선택사항)
            str network_acl_name: Network ACL 이름(선택사항)
            str network_acl_status_code: Network ACL 상태 코드(선택사항)
            list network_acl_no_list: Network ACL 번호 리스트(선택사항)
            str vpc_no: VPC 번호(선택사항)

        Returns:
            Dict: Network ACL 목록 응답
        """
    
        params = {
            'responseFormatType': responseFormatType
        }       
        if region_code is not None:
            params['regionCode'] = region_code
        if network_acl_name is not None:
            params['networkAclName'] = network_acl_name
        if network_acl_status_code is not None:
            params['networkAclStatusCode'] = network_acl_status_code
        if network_acl_no_list is not None:
            for idx, network_acl_no in enumerate(network_acl_no_list, start=1):
                params[f'networkAclNoList.{idx}'] = network_acl_no
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if vpc_no is not None:
            params['vpcNo'] = vpc_no
        return self.client.get('/getNetworkAclList', params=params)

    def get_network_acl_detail(
        self,
        network_acl_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        Network ACL 번호를 지정하여 Network ACL의 상세 정보를 조회합니다.

        args:
            str network_acl_no: Network ACL 번호
            str region_code: 리전 코드(선택사항)

        Returns:
            Dict: Network ACL 상세 정보 응답
        """
        params = {
            'networkAclNo': network_acl_no,
            'responseFormatType': responseFormatType
        }
        if region_code is not None:
            params['regionCode'] = region_code
        return self.client.get('/getNetworkAclDetail', params=params)

    def get_network_acl_rule_list(
        self,
        network_acl_no: str,
        region_code: Optional[str] = None,
        network_acl_rule_type_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        Network ACL 번호를 지정하여 Network ACL의 규칙 목록을 조회합니다.

        args:
            str network_acl_no: Network ACL 번호
            str region_code: 리전 코드(선택사항)
            str network_acl_rule_type_code: Network ACL 규칙 타입 코드(선택사항)

        Returns:
            Dict: Network ACL 규칙 목록 응답
        """
        params = {
            'networkAclNo': network_acl_no,
            'responseFormatType': responseFormatType
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if network_acl_rule_type_code:
            params['networkAclRuleTypeCode'] = network_acl_rule_type_code
        return self.client.get('/getNetworkAclRuleList', params=params)

    def get_network_acl_deny_allow_group_list(
        self,
        region_code: Optional[str] = None,
        vpc_no: Optional[str] = None,
        network_acl_deny_allow_group_name: Optional[str] = None,
        network_acl_deny_allow_group_status_code: Optional[str] = None,
        network_acl_deny_allow_group_no_list: Optional[List[str]] = None,
        is_applied: Optional[bool] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        Network ACL 번호를 지정하여 Network ACL의 규칙 목록을 조회합니다.

        args:
            str region_code: 리전 코드(선택사항)
            str vpc_no: VPC 번호(선택사항)
            str network_acl_deny_allow_group_name: Network ACL 규칙 이름(선택사항)
            str network_acl_deny_allow_group_status_code: Network ACL 규칙 상태 코드(선택사항)
            list network_acl_deny_allow_group_no_list: Network ACL 규칙 번호 리스트(선택사항)
            bool is_applied: 적용 여부(선택사항)
            int page_no: 페이지 번호(선택사항)
            int page_size: 페이지 크기(선택사항) 

        Returns:
            Dict: Network ACL 규칙 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType
        }
        if region_code is not None: 
            params['regionCode'] = region_code
        if vpc_no is not None:
            params['vpcNo'] = vpc_no
        if network_acl_deny_allow_group_name is not None:
            params['networkAclDenyAllowGroupName'] = network_acl_deny_allow_group_name
        if network_acl_deny_allow_group_status_code is not None:
            params['networkAclDenyAllowGroupStatusCode'] = network_acl_deny_allow_group_status_code
        if network_acl_deny_allow_group_no_list is not None:
            for idx, network_acl_deny_allow_group_no in enumerate(network_acl_deny_allow_group_no_list, start=1):
                params[f'networkAclDenyAllowGroupNoList.{idx}'] = network_acl_deny_allow_group_no
        if is_applied is not None:
            params['isApplied'] = is_applied
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        return self.client.get('/getNetworkAclDenyAllowGroupList', params=params)


    def get_network_acl_deny_allow_group_detail(
        self,
        network_acl_deny_allow_group_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        Network ACL 규칙 번호를 지정하여 Network ACL의 규칙 상세 정보를 조회합니다.

        args:
            str network_acl_deny_allow_group_no: Network ACL 규칙 번호
            str region_code: 리전 코드(선택사항)

        Returns:
            Dict: Network ACL 규칙 상세 정보 응답
        """
        params = {
            'networkAclDenyAllowGroupNo': network_acl_deny_allow_group_no,
            'responseFormatType': responseFormatType
        }
        if region_code is not None:
            params['regionCode'] = region_code
        return self.client.get('/getNetworkAclDenyAllowGroupDetail', params=params)
    """
    ================================================================
    NATGW 인스턴스 관련 API
    ================================================================
    """
    def get_nat_gateway_instance_list(
        self,
        region_code: Optional[str] = None,
        zone_code: Optional[str] = None,
        nat_gateway_instance_no_list: Optional[List[str]] = None,
        public_ip: Optional[str] = None,
        vpc_name: Optional[str] = None,
        nat_gateway_name: Optional[str] = None,
        nat_gateway_instance_status_code: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        output: Optional[str] = None,
        subnet_name: Optional[str] = None,
        private_ip: Optional[str] = None,
        nat_gateway_type_code: Optional[str] = None,
        responseFormatType: str = 'json'

    ) -> Dict:
        """
        NATGW 인스턴스 목록을 조회합니다.

        args:
            str region_code: 리전 코드(선택사항)
            str zone_code: 존 코드(선택사항)
            list nat_gateway_instance_no_list: NATGW 인스턴스 번호 리스트(선택사항)
            str public_ip: 퍼블릭 IP(선택사항)
            str vpc_name: VPC 이름(선택사항)
            str nat_gateway_name: NATGW 이름(선택사항)
            str nat_gateway_instance_status_code: NATGW 인스턴스 상태 코드(선택사항) #INIT | RUN | SET | TERMTING
            int page_no: 페이지 번호(선택사항)
            int page_size: 페이지 크기(선택사항)
            str output: 출력 형식(선택사항)
            str subnet_name: 서브넷 이름(선택사항)
            str private_ip: 사설 IP(선택사항)
            str nat_gateway_type_code: NATGW 타입 코드(선택사항) #PRVT | PBLIP PRVT: Private NAT Gateway PBLIP: Public NAT Gateway

        Returns:
            Dict: NATGW 인스턴스 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType
        }

        if region_code is not None:
            params['regionCode'] = region_code
        if zone_code is not None:
            params['zoneCode'] = zone_code
        if nat_gateway_instance_no_list is not None:
            for idx, nat_gateway_instance_no in enumerate(nat_gateway_instance_no_list, start=1):
                params[f'natGatewayInstanceNoList.{idx}'] = nat_gateway_instance_no
        if public_ip is not None:
            params['publicIp'] = public_ip
        if vpc_name is not None:
            params['vpcName'] = vpc_name
        if nat_gateway_name is not None:
            params['natGatewayName'] = nat_gateway_name
        if nat_gateway_instance_status_code is not None:
            params['natGatewayInstanceStatusCode'] = nat_gateway_instance_status_code
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if output is not None:
            params['output'] = output
        if subnet_name is not None:
            params['subnetName'] = subnet_name
        if private_ip is not None:
            params['privateIp'] = private_ip
        if nat_gateway_type_code is not None:
            params['natGatewayTypeCode'] = nat_gateway_type_code
        return self.client.get('/getNatGatewayInstanceList', params=params)

    def get_nat_gateway_instance_detail(
        self,
        nat_gateway_instance_no: str,
        region_code: Optional[str] = None,
        output: Optional[str] = 'json'
    ) -> Dict:
        """
        NATGW 인스턴스 상세 정보를 조회합니다.

        args:
            str nat_gateway_instance_no: NATGW 인스턴스 번호
            str region_code: 리전 코드(선택사항)

        Returns:
            Dict: NATGW 인스턴스 상세 정보 응답 
        """
        params = {
            'natGatewayInstanceNo': nat_gateway_instance_no,
         
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if output is not None:
            params['output'] = output
        return self.client.get('/getNatGatewayInstanceDetail', params=params)


    """
    ================================================================
    VPC Peer 관련 API
    ================================================================
    """

    def get_vpc_peering_instance_list(
        self, 
        region_code: Optional[str] = None,
        vpc_peering_instance_no_list: Optional[List[str]] = None,
        source_vpc_name: Optional[str] = None,
        target_vpc_name: Optional[str] = None,
        vpc_peering_name: Optional[str] = None,
        vpc_peering_instance_status_code: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        sorted_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        VPC Peer 인스턴스 목록을 조회합니다.

        args:
            str region_code: 리전 코드(선택사항)
            list vpc_peering_instance_no_list: VPC Peer 인스턴스 번호 리스트(선택사항)
            str source_vpc_name: 소스 VPC 이름(선택사항)
            str target_vpc_name: 타겟 VPC 이름(선택사항)
            str vpc_peering_name: VPC Peer 이름(선택사항)
            str vpc_peering_instance_status_code: VPC Peer 인스턴스 상태 코드(선택사항) (INIT | RUN | TERMTING)
            int page_no: 페이지 번호(선택사항)
            int page_size: 페이지 크기(선택사항)
            str sorted_by: 정렬 기준(선택사항) (vpcPeeringInstanceName | createDate)
            str sort_order: 정렬 순서(선택사항) (ASC | DESC)

        Returns:
            Dict: VPC Peer 인스턴스 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if vpc_peering_instance_no_list is not None:
            for idx, vpc_peering_instance_no in enumerate(vpc_peering_instance_no_list, start=1):
                params[f'vpcPeeringInstanceNoList.{idx}'] = vpc_peering_instance_no
        if source_vpc_name is not None:
            params['sourceVpcName'] = source_vpc_name
        if target_vpc_name is not None:
            params['targetVpcName'] = target_vpc_name
        if vpc_peering_name is not None:
            params['vpcPeeringName'] = vpc_peering_name
        if vpc_peering_instance_status_code is not None:
            params['vpcPeeringInstanceStatusCode'] = vpc_peering_instance_status_code
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if sorted_by is not None:
            params['sortedBy'] = sorted_by
        if sort_order is not None:
            params['sortOrder'] = sort_order
        return self.client.get('/getVpcPeeringInstanceList', params=params)
        
    def get_vpc_peering_instance_detail(
        self,
        vpc_peering_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        VPC Peer 인스턴스 상세 정보를 조회합니다.

        args:
            str vpc_peering_instance_no: VPC Peer 인스턴스 번호
            str region_code: 리전 코드(선택사항)

        Returns:
            Dict: VPC Peer 인스턴스 상세 정보 응답
        """
        params = {
            'vpcPeeringInstanceNo': vpc_peering_instance_no,
            'responseFormatType': responseFormatType
        }
        if region_code is not None:
            params['regionCode'] = region_code
        return self.client.get('/getVpcPeeringInstanceDetail', params=params)

    """
    ================================================================
    Route Table 관련 API
    ================================================================
    """
    def get_route_table_list(
        self,
        region_code: Optional[str] = None,
        route_table_no_list: Optional[List[str]] = None,
        route_table_name: Optional[str] = None,
        supported_subnet_type_code: Optional[str] = None,
        vpc_no: Optional[str] = None,
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        sorted_by: Optional[str] = None,
        sort_order: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        Route Table 목록을 조회합니다.

        args:
            str region_code: 리전 코드(선택사항)
            list route_table_no_list: Route Table 번호 리스트(선택사항)
            str route_table_name: Route Table 이름(선택사항)
            str supported_subnet_type_code: 지원 서브넷 타입 코드(선택사항) (PUBLIC | PRIVATE)
            str vpc_no: VPC 번호(선택사항)
            int page_no: 페이지 번호(선택사항)
            int page_size: 페이지 크기(선택사항)
            str sorted_by: 정렬 기준(선택사항) (routeTableName | route
            str sort_order: 정렬 순서(선택사항) (ASC | DESC)
            str responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)
            
        Returns:
            Dict: Route Table 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if route_table_no_list is not None:
            for idx, route_table_no in enumerate(route_table_no_list, start=1):
                params[f'routeTableNoList.{idx}'] = route_table_no
        if route_table_name is not None:
            params['routeTableName'] = route_table_name
        if supported_subnet_type_code is not None:
            params['supportedSubnetTypeCode'] = supported_subnet_type_code
        if vpc_no is not None:
            params['vpcNo'] = vpc_no
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if sorted_by is not None:
            params['sortedBy'] = sorted_by
        if sort_order is not None:
            params['sortOrder'] = sort_order
        return self.client.get('/getRouteTableList', params=params)

    def get_route_table_detail(
        self,
        route_table_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        Route Table 상세 정보를 조회합니다.

        args:
            str route_table_no: Route Table 번호
            str region_code: 리전 코드(선택사항)
            
        Returns:
            Dict: Route Table 상세 정보 응답
        """
        params = {  
            'routeTableNo': route_table_no,
            'responseFormatType': responseFormatType
        }
        if region_code is not None:
            params['regionCode'] = region_code
        return self.client.get('/getRouteTableDetail', params=params)
        
        
    def get_route_list(
        self,
        route_table_no: str,
        vpc_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json',
        ) -> Dict:
        """
        Route Table 번호를 지정하여 Route 목록을 조회합니다.

        args:
            str route_table_no: Route Table 번호
            str vpc_no: VPC 번호
            str region_code: 리전 코드(선택사항)

        Returns:
            Dict: Route 목록 응답
        """
        params = {
            'routeTableNo': route_table_no,
            'vpcNo': vpc_no,
            'responseFormatType': responseFormatType
        }
        if region_code is not None:
            params['regionCode'] = region_code
        return self.client.get('/getRouteList', params=params)

    def get_route_table_subnet_list(
        self,
        route_table_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        Route Table 번호를 지정하여 Route Table 서브넷 목록을 조회합니다.

        args:
            str route_table_no: Route Table 번호
            str region_code: 리전 코드(선택사항)

        Returns:
            Dict: Route Table 서브넷 목록 응답
        """

        params = {
            'routeTableNo': route_table_no,
            'responseFormatType': responseFormatType
        }
        if region_code is not None:
            params['regionCode'] = region_code
        return self.client.get('/getRouteTableSubnetList', params=params)

   