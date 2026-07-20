from typing import Dict, List, Optional
from ncp_api.base import BaseNCPAPI


class LoadbalancerAPI(BaseNCPAPI):
    """
    Load Balancer API 클래스

    """
    ENDPOINT_KEY = "loadbalancer"
  
    
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
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        sortlist_sorted_by: Optional[List[str]] = None,
        sortlist_sorting_order: Optional[List[str]] = None,
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
            int page_no: 페이지 번호(선택사항)
            int page_size: 페이지 크기(선택사항)
            list sortlist_sorted_by: 정렬 기준 리스트(선택사항) (loadBalancerInstanceName)
            list sortlist_sorting_order: 정렬 순서 리스트(선택사항) (ASC | DESC)
            responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)

        Returns:
            Dict: Load Balancer 인스턴스 목록 응답
        """
        params = {
            'responseFormatType': responseFormatType
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if vpc_no is not None:
            params['vpcNo'] = vpc_no
        if load_balancer_code is not None:
            params['loadBalancerCode'] = load_balancer_code
        if load_balancer_network_type_code is not None:
            params['loadBalancerNetworkTypeCode'] = load_balancer_network_type_code
        if load_balancer_instance_no_list is not None:
            for idx, load_balancer_instance_no in enumerate(load_balancer_instance_no_list, start=1):
                params[f'loadBalancerInstanceNoList.{idx}'] = load_balancer_instance_no
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if sortlist_sorted_by and sortlist_sorting_order:
            if len(sortlist_sorted_by) != len(sortlist_sorting_order):
                raise ValueError("sortlist_sorted_by와 sortlist_sorting_order의 길이가 다릅니다.")

            for idx, (sorted_by, sorting_order) in enumerate(
                zip(sortlist_sorted_by, sortlist_sorting_order),
                start=1
            ):
                params[f"sortList.{idx}.sortedBy"] = sorted_by
                params[f"sortList.{idx}.sortingOrder"] = sorting_order

        return self.client.get('/getLoadBalancerInstanceList', params=params)


    def get_load_balancer_instance_detail(
        self,
        load_balancer_instance_no: str,
        region_code: Optional[str] = None,
        responseFormatType: Optional[str] = 'json'
    ) -> Dict:
        """
        Load Balancer 인스턴스 상세 정보를 조회합니다.

        args:
            str load_balancer_instance_no: Load Balancer 인스턴스 번호
            str region_code: 리전 코드(선택사항)
            str responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)


        Returns:
            Dict: Load Balancer 인스턴스 상세 정보 응답
        """
        params = {
            'loadBalancerInstanceNo': load_balancer_instance_no
            
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

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
            str responseFormatType: 응답 포맷 타입 (json 또는 xml, 기본값: json)

        Returns:
            Dict: Load Balancer 리스너 목록 응답
        """
        params = {
            'loadBalancerInstanceNo': load_balancer_instance_no
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType

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
        if region_code is not None:
            params['regionCode'] = region_code
        return self.client.get('/getLoadBalancerRuleList', params=params)

    def get_load_balancer_listener_certificate_list(
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
            'loadBalancerListenerNo': load_balancer_listener_no
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
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
        page_no: Optional[int] = None,
        page_size: Optional[int] = None,
        sortlist_sorted_by: Optional[List[str]] = None,
        sortlist_sorting_order: Optional[List[str]] = None,
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
        if region_code is not None:
            params['regionCode'] = region_code
        if vpc_no is not None:
            params['vpcNo'] = vpc_no
        if target_type_code is not None:
            params['targetTypeCode'] = target_type_code
        if target_group_no_list is not None:
            for idx, target_group_no in enumerate(target_group_no_list, start=1):
                params[f'targetGroupNoList.{idx}'] = target_group_no
        if page_no is not None:
            params['pageNo'] = page_no
        if page_size is not None:
            params['pageSize'] = page_size
        if sortlist_sorted_by and sortlist_sorting_order:
            if len(sortlist_sorted_by) != len(sortlist_sorting_order):
                raise ValueError("sortlist_sorted_by와 sortlist_sorting_order의 길이가 다릅니다.")

            for idx, (sorted_by, sorting_order) in enumerate(
                zip(sortlist_sorted_by, sortlist_sorting_order),
                start=1
            ):
                params[f"sortList.{idx}.sortedBy"] = sorted_by
                params[f"sortList.{idx}.sortingOrder"] = sorting_order
        
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
            'targetGroupNo': target_group_no
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
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
            'targetGroupNo': target_group_no
            
        }
        if region_code is not None:
            params['regionCode'] = region_code
        if responseFormatType is not None:
            params['responseFormatType'] = responseFormatType
        return self.client.get('/getTargetList', params=params)
