"""
Network 리소스 API 모듈

Network 인스턴스 및 관련 정보를 조회하는 API 모듈입니다.
VPC, SUBNET, NACL, NATGW, VPC peer, Route Table 등 네트워크 관련 리소스를 조회합니다.


"""

from bisect import insort_right
from typing import Dict, List, Optional
from utils.common_rest import NCPBaseClient


class NetworkAPI:
    """
    Network 리소스 API 클래스
    
    Network 인스턴스 및 관련 정보를 조회합니다.
    """
    
    def __init__(self, client: NCPBaseClient):
        """
        NetworkAPI를 초기화합니다.
        
        Args:
            client: NCPBaseClient 인스턴스
        """
        self.client = client
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

        Returns:
            Dict: VPC 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType
        }
        if region_code:
            params['regionCode'] = region_code
        if vpc_status_code:
            params['vpcStatusCode'] = vpc_status_code
        if vpc_name:
            params['vpcName'] = vpc_name
        if vpc_no_list:
            params['vpcNoList'] = vpc_no_list
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
        if region_code:
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
            str subnet_status_code: SUBNET 상태 코드(선택사항)
            str vpc_no: VPC 번호(선택사항)
            str zone_code: 존 코드(선택사항)

        Returns:
            Dict: SUBNET 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType
        }
        if region_code:
            params['regionCode'] = region_code
        if subnet_no_list:
            params['subnetNoList'] = subnet_no_list
        if subnet_name:
            params['subnetName'] = subnet_name
        if subnet:
            params['subnet'] = subnet
        if subnet_type_code:
            params['subnetTypeCode'] = subnet_type_code
        if usage_type_code:
            params['usageTypeCode'] = usage_type_code
        if network_acl_no:
            params['networkAclNo'] = network_acl_no
        if subnet_status_code:
            params['subnetStatusCode'] = subnet_status_code
        if vpc_no:
            params['vpcNo'] = vpc_no
        if zone_code:
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
        if region_code:
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
        if region_code:
            params['regionCode'] = region_code
        if network_acl_name:
            params['networkAclName'] = network_acl_name
        if network_acl_status_code:
            params['networkAclStatusCode'] = network_acl_status_code
        if network_acl_no_list:
            params['networkAclNoList'] = network_acl_no_list
        if vpc_no:
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
        if region_code:
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
        if region_code:
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

        Returns:
            Dict: Network ACL 규칙 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType
        }
        if region_code: 
            params['regionCode'] = region_code
        if vpc_no:
            params['vpcNo'] = vpc_no
        if network_acl_deny_allow_group_name:
            params['networkAclDenyAllowGroupName'] = network_acl_deny_allow_group_name
        if network_acl_deny_allow_group_status_code:
            params['networkAclDenyAllowGroupStatusCode'] = network_acl_deny_allow_group_status_code
        if network_acl_deny_allow_group_no_list:
            params['networkAclDenyAllowGroupNoList'] = network_acl_deny_allow_group_no_list
        if is_applied:
            params['isApplied'] = is_applied
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
        if region_code:
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

        if region_code:
            params['regionCode'] = region_code
        if zone_code:
            params['zoneCode'] = zone_code
        if nat_gateway_instance_no_list:
            params['natGatewayInstanceNoList'] = nat_gateway_instance_no_list
        if public_ip:
            params['publicIp'] = public_ip
        if vpc_name:
            params['vpcName'] = vpc_name
        if nat_gateway_name:
            params['natGatewayName'] = nat_gateway_name
        if nat_gateway_instance_status_code:
            params['natGatewayInstanceStatusCode'] = nat_gateway_instance_status_code
        if output:
            params['output'] = output
        if subnet_name:
            params['subnetName'] = subnet_name
        if private_ip:
            params['privateIp'] = private_ip
        if nat_gateway_type_code:
            params['natGatewayTypeCode'] = nat_gateway_type_code
        return self.client.get('/getNatGatewayInstanceList', params=params)

    def get_nat_gateway_instance_detail(
        self,
        nat_gateway_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
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
            'responseFormatType': responseFormatType
        }
        if region_code:
            params['regionCode'] = region_code
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

        Returns:
            Dict: VPC Peer 인스턴스 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType
        }
        if region_code:
            params['regionCode'] = region_code
        if vpc_peering_instance_no_list:
            params['vpcPeeringInstanceNoList'] = vpc_peering_instance_no_list
        if source_vpc_name:
            params['sourceVpcName'] = source_vpc_name
        if target_vpc_name:
            params['targetVpcName'] = target_vpc_name
        if vpc_peering_name:
            params['vpcPeeringName'] = vpc_peering_name
        if vpc_peering_instance_status_code:
            params['vpcPeeringInstanceStatusCode'] = vpc_peering_instance_status_code
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
        if region_code:
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
            
        Returns:
            Dict: Route Table 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType
        }
        if region_code:
            params['regionCode'] = region_code
        if route_table_no_list:
            params['routeTableNoList'] = route_table_no_list
        if route_table_name:
            params['routeTableName'] = route_table_name
        if supported_subnet_type_code:
            params['supportedSubnetTypeCode'] = supported_subnet_type_code
        if vpc_no:
            params['vpcNo'] = vpc_no
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
        if region_code:
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
        if region_code:
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
        if region_code:
            params['regionCode'] = region_code
        return self.client.get('/getRouteTableSubnetList', params=params)
    
    """
    ================================================================
    Load Balancer 관련 API
    ================================================================
    """

    def get_load_balancer_instance_list(
        self,
        region_code: Optional[str] = None,
        vpc_no: Optional[str] = None,
        load_balancer_code: Optional[str] = None,
        load_balancer_network_type_code: Optional[str] = None,
        load_balancer_instance_no_list: Optional[List[str]] = None,

        responseFormatType: str = 'json'
    ) -> Dict:
        """
        Load Balancer 인스턴스 목록을 조회합니다.

        args:
            str region_code: 리전 코드(선택사항)
            str vpc_no: VPC 번호(선택사항)
            str load_balancer_code: Load Balancer 코드(선택사항) (APPLICATION | NETWORK | NETWORK_PROXY)
            str load_balancer_network_type_code: Load Balancer 네트워크 타입 코드(선택사항) (PUBLIC | PRIVATE)
            list load_balancer_instance_no_list: Load Balancer 인스턴스 번호 리스트(선택사항)

        Returns:
            Dict: Load Balancer 인스턴스 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType
        }
        if region_code:
            params['regionCode'] = region_code
        if vpc_no:
            params['vpcNo'] = vpc_no
        if load_balancer_code:
            params['loadBalancerCode'] = load_balancer_code
        if load_balancer_network_type_code:
            params['loadBalancerNetworkTypeCode'] = load_balancer_network_type_code
        if load_balancer_instance_no_list:
            params['loadBalancerInstanceNoList'] = load_balancer_instance_no_list
        return self.client.get('/getLoadBalancerInstanceList', params=params)


    def get_load_balancer_instance_detail(
        self,
        load_balancer_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        Load Balancer 인스턴스 상세 정보를 조회합니다.

        args:
            str load_balancer_instance_no: Load Balancer 인스턴스 번호
            str region_code: 리전 코드(선택사항)

        Returns:
            Dict: Load Balancer 인스턴스 상세 정보 응답
        """
        params = {
            'loadBalancerInstanceNo': load_balancer_instance_no,
            'responseFormatType': responseFormatType
        }
        if region_code:
            params['regionCode'] = region_code
        return self.client.get('/getLoadBalancerInstanceDetail', params=params)

    def get_load_balancer_listener_list(
        self,
        load_balancer_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        Load Balancer 리스너 목록을 조회합니다.

        args:
            str load_balancer_instance_no: Load Balancer 인스턴스 번호
            str region_code: 리전 코드(선택사항)

        Returns:
            Dict: Load Balancer 리스너 목록 응답
        """
        params = {
            'loadBalancerInstanceNo': load_balancer_instance_no,
            'responseFormatType': responseFormatType
        }
        if region_code:
            params['regionCode'] = region_code
        return self.client.get('/getLoadBalancerListenerList', params=params)

    def get_load_balancer_rule_list(
        self,
        load_balancer_listener_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        Load Balancer 규칙 목록을 조회합니다.

        args:
            str load_balancer_listener_no: Load Balancer 리스너 번호
            str region_code: 리전 코드(선택사항)

        Returns:
            Dict: Load Balancer 규칙 목록 응답
        """
        params = {
            'loadBalancerListenerNo': load_balancer_listener_no,
            'responseFormatType': responseFormatType
        }
        if region_code:
            params['regionCode'] = region_code
        return self.client.get('/getLoadBalancerRuleList', params=params)

    def get_load_balancer_listener_Certificate_list(
        self,
        load_balancer_listener_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        Load Balancer 리스너 인증서 목록을 조회합니다.

        args:
            str load_balancer_listener_no: Load Balancer 리스너 번호
            str region_code: 리전 코드(선택사항)

        Returns:
            Dict: Load Balancer 리스너 인증서 목록 응답
        """
        params = {
            'loadBalancerListenerNo': load_balancer_listener_no,
            'responseFormatType': responseFormatType
        }
        if region_code:
            params['regionCode'] = region_code
        return self.client.get('/getLoadBalancerListenerCertificateList', params=params)

    """
    ================================================================
    Target Group 관련 API
    ================================================================
    """

    def get_target_group_list(
        self,
        region_code: Optional[str] = None,
        vpc_no: Optional[str] = None,
        target_type_code: Optional[str] = None,
        target_group_no_list: Optional[List[str]] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        Target Group 목록을 조회합니다.

        args:
            str region_code: 리전 코드(선택사항)
            str vpc_no: VPC 번호(선택사항)
            str target_type_code: Target 타입 코드(선택사항) (VSVR)
            list target_group_no_list: Target Group 번호 리스트(선택사항)

        Returns:
            Dict: Target Group 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType
        }
        if region_code:
            params['regionCode'] = region_code
        if vpc_no:
            params['vpcNo'] = vpc_no
        if target_type_code:
            params['targetTypeCode'] = target_type_code
        if target_group_no_list:
            params['targetGroupNoList'] = target_group_no_list
        return self.client.get('/getTargetGroupList', params=params)

    def get_target_group_detail(
        self,
        target_group_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """
        Target Group 상세 정보를 조회합니다.

        args:
            str target_group_no: Target Group 번호
            str region_code: 리전 코드(선택사항)

        Returns:
            Dict: Target Group 상세 정보 응답
        """
        params = {
            'targetGroupNo': target_group_no,
            'responseFormatType': responseFormatType
        }
        if region_code:
            params['regionCode'] = region_code
        return self.client.get('/getTargetGroupDetail', params=params)

    def get_target_list(
        self,
        target_group_no: str,
        region_code: Optional[str] = None,
        responseFormatType: str = 'json'
    ) -> Dict:
        """ 
        Target Group 목록을 조회합니다.

        args:
            str target_group_no: Target Group 번호
            str region_code: 리전 코드(선택사항)

        Returns:
            Dict: Target Group 목록 응답
        """
        params = {
            'targetGroupNo': target_group_no,
            'responseFormatType': responseFormatType
        }
        if region_code:
            params['regionCode'] = region_code
        return self.client.get('/getTargetList', params=params)

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
        if domain_id:
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
        params = {
           'searchContent': search_content,
           'lbRegionCode': lb_region_code
        }
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
