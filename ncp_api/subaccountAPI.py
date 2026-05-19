from typing import Dict, List, Optional, Any
from utils.common_rest import NCPBaseClient
from ncp_api.base import BaseNCPAPI


class SubAccountAPI(BaseNCPAPI):
    """
    Cloud Subaccount API 클래스

    """
    """
    ================================================================
    SubAccount API
    ================================================================
    """
    def get_subaccount_list(
            self,
            search_column : Optional[str] = None,
            search_word : Optional[str] = None,
            page : Optional[int] = None,
            size : Optional[int] = None

    ) -> Dict:
        """
        서브 계정 목록을 조회합니다.

        args:
            str search_column: 검색 컬럼  (loginId | name | subAccountNo) (loginId: 서브 계정 로그인 아이디 name: 서브 계정 이름 subAccountNo: 서브 계정 번호 )
            str search_word: 검색 키워드
            int page: 페이지 
            int size: 페이지 사이즈
        Returns:
            Dict: 서브 계정 목록
                
        """
        params = {}
        if search_column is not None:
            params['searchColumn'] = search_column
        if search_word is not None:
            params['searchWord'] = search_word
        if page is not None:
            params['page'] = page
        if size is not None:
            params['size'] = size

        return self.get(f'/api/v1/sub-accounts', params=params)
    
    def get_subaccount_detail(
            self,
            subaccount_id: str 

    ) -> Dict:
        """
        Sub Account API에서 공통으로 사용하는 헤더에 대한 정보는 Sub Account 요청 헤더를 참조해 주십시오

        args:
            str subaccount_id: 서브어카운트 ID
        Returns:
            Dict: 서브 계정 상세
                
        """
        params = {}
        

        return self.get(f'/api/v1/sub-accounts/{subaccount_id}', params=params)
    
    def get_access_key(
            self,
            subaccount_id: str 

    ) -> Dict:
        """
        서브 계정의 Access Key를 조회합니다.

        args:
            str subaccount_id: 서브어카운트 ID
        Returns:
            Dict: 서브 계정의 Access Key를 조회합니다.
                
        """
        params = {}
        

        return self.get(f'/api/v1/sub-accounts/{subaccount_id}/access-keys', params=params)
    
    def get_login_alias(
            self
    ) -> Dict:
        """
        서브 계정 로그인 접속키를 조회합니다.

        args:
            None
        Returns:
            Dict: 서브 계정의 login Alias
                
        """
        params = {}
        

        return self.get(f'/api/v1/login-alias', params=params)
    
    def get_session_timeout(
            self
    ) -> Dict:
        """
        서브 계정 유휴 타임아웃 설정을 조회합니다.

        args:
            None
        Returns:
            Dict: 서브 계정 유휴 타임아웃 설정을 조회합니다.
                
        """
        params = {}
        

        return self.get(f'/api/v1/tenant-settings/sub-account-session-policy', params=params)
    
    def get_account_password_policy(
            self
    ) -> Dict:
        """
        서브 계정의 로그인 비밀번호 만료일(변경 주기)을 조회합니다.

        args:
            None
        Returns:
            Dict: 서브 계정의 로그인 비밀번호 만료일(변경 주기)을 조회합니다.
                
        """
        params = {}
        

        return self.get(f'/api/v1/tenant-settings/sub-account-password-policy', params=params)
    
    def get_account_idle_disable_policy(
            self
    ) -> Dict:
        """
        장기 미사용 서브계정 비활성화 조회

        args:
            None

        Returns:
            Dict: 장기 미사용 서브계정 비활성화 조회
                
        """
        params = {}
        

        return self.get(f'/api/v1/tenant-settings/idle-disable-settings', params=params)
    
    def get_account_last_access(
            self,
            sub_account_id: str
    ) -> Dict:
        """
        서브계정 최종 접속 정보 조회 

        args:
            sub_account_id

        Returns:
            Dict: 서브계정 최종 접속 정보 조회 

                
        """
        params = {}
        

        return self.get(f'/api/v1/users/{sub_account_id}/last-access-summary', params=params)
    

    def get_account_accees_rule(
            self,
            sub_account_id: str
    ) -> Dict:
        """
        서브 계정의 콘솔 접근 규칙을 조회합니다.

        args:
            sub_account_id

        Returns:
            Dict: 서브 계정의 콘솔 접근 규칙을 조회합니다.

                
        """
        params = {}
        

        return self.get(f'/api/v1/sub-accounts/{sub_account_id}/access-rules/console', params=params)
    
    def get_apikey_accees_rule(
            self,
            sub_account_id: str
    ) -> Dict:
        """
        서브 API 키의 콘솔 접근 규칙을 조회합니다.

        args:
            sub_account_id

        Returns:
            Dict: 서브 API 키의 콘솔 접근 규칙을 조회합니다.

                
        """
        params = {}
        

        return self.get(f'/api/v1/sub-accounts/{sub_account_id}/access-rules/api', params=params)
    
    def get_multi_factor_accees_rule(
            self,
            sub_account_id: str
    ) -> Dict:
        """
        서브 계정의 2차 인증 정보를 조회합니다.

        args:
            sub_account_id

        Returns:
            Dict: 서브 계정의 2차 인증 정보를 조회합니다.

                
        """
        params = {}
        

        return self.get(f'/api/v1/sub-accounts/{sub_account_id}/mfa', params=params)
    
    def get_account_tag(
            self,
            sub_account_id: str
    ) -> Dict:
        """
        서브 계정에 추가된 태그를 조회합니다.

        args:
            sub_account_id

        Returns:
            Dict: 서브 계정에 추가된 태그를 조회합니다.

                
        """
        params = {}
        

        return self.get(f'/api/v1/users/{sub_account_id}/tags', params=params)
    
    def get_account_info(
            self,
            sub_account_id: str
    ) -> Dict:
        """
        서브 계정, 삭제된 서브 계정, 역할 사용자 등 계정에 권한이 부여된 서브 계정의 사용자 정보를 조회합니다.

        args:
            sub_account_id

        Returns:
            Dict: 서브 계정, 삭제된 서브 계정, 역할 사용자 등 계정에 권한이 부여된 서브 계정의 사용자 정보를 조회합니다.

                
        """
        params = {}
        

        return self.get(f'/api/v1/users/{sub_account_id}', params=params)
    
    def get_account_id_with_no(
            self,
            sub_account_no: list[str]
    ) -> Dict:
        """
        서브 계정 번호를 사용하여 서브 계정 아이디를 조회합니다.

        args:
            list sub_account_no: 

        Returns:
            Dict: 서브 계정 번호를 사용하여 서브 계정 아이디를 조회합니다.

                
        """
        params = {'subAccountNo': ",".join(map(str, sub_account_no))}
        


        

        return self.get(f'/api/v1/sub-accounts-with-no', params=params)
    
    """
    ================================================================
    SubAccount Group API
    ================================================================
    """

    def get_account_group(
            self,
            page: Optional[int] = None,
            size: Optional[int] = None,
            
    ) -> Dict:
        """
        그룹 목록을 조회합니다.

        args:
            int page: 페이지 
            int size: 페이지 사이즈

        Returns:
            Dict: 그룹 목록을 조회합니다.

                
        """
        params = {}

        if page is not None:
            params['page'] = page
        if size is not None:
            params['size'] = size

        
        return self.get(f'/api/v1/groups', params=params)
    
    def get_account_group_detail(
            self,
            group_id: str
            
    ) -> Dict:
        """
        그룹 목록을 조회합니다.

        args:
            str group_id : 그룹 아이디

        Returns:
            Dict: 그룹 상세를 조회합니다.

                
        """
        params = {}
             
        return self.get(f'/api/v1/groups/{group_id}', params=params)
    
    def get_account_group_tag(
            self,
            group_id: str
            
    ) -> Dict:
        """
        그룹 태그를 조회합니다.

        args:
            str group_id : 그룹 아이디

        Returns:
            Dict: 그룹 태그를 조회합니다.

                
        """
        params = {}
             
        return self.get(f'/api/v1/groups/{group_id}/tags', params=params)
    
    """
    ================================================================
    SubAccount Policy API
    ================================================================
    """
    def get_account_policy_list(
            self,
            page: Optional[int] = None,
            size: Optional[int] = None,
            search_column: Optional[str] = None,
            search_word: Optional[str] = None,
            type: Optional[str] = None
            
    ) -> Dict:
        """
        정책 목록을 조회합니다.

        args:
            str group_id : 그룹 아이디
            int page : 페이지
            int size : 페이지 사이즈
            str search_column : 검색 컬럼 (policyName)
            str search_word : 검색 키워드
            str type : 검색유형 (SYSTEM_MANAGED | USER_CREATED) (SYSTEM_MANAGED: 관리형 정책 USER_CREATED: 사용자 정의 정책)
)

        Returns:
            Dict: 정책 목록을 조회합니다.

                
        """
        params = {}

        if page is not None:
            params['page'] = page
        if size is not None:
            params['size'] = size
        if search_column is not None:
            params['searchColumn'] = search_column
        if search_word is not None:
            params['searchWord'] = search_word
        if type is not None:
            params['type'] = type
             
        return self.get(f'/api/v1/policies', params=params)
    
    def get_account_policy_detail(
            self,
            policy_id : str, 
            with_permissions : Optional[bool] = None
            
    ) -> Dict:
        """
        정책 목록을 조회합니다.

        args:
            str policy_id : 정책번호
            bool with_permissions : 정책의 상세 권한 표시 여부 (true | false (기본값)) (true: 표시 false: 표시 안 함)

        Returns:
            Dict: 정책 목록을 조회합니다.

                
        """
        params = {}
        if with_permissions is not None:
            params['withPermissions'] = with_permissions
             
        return self.get(f'/api/v1/policies/{policy_id}', params=params)
    
    def get_account_policy_validation(
            self,
            policy_name : str,
            permissions : list[dict[str, Any]],
            description : Optional[str] = None           
    ) -> Dict:
        """
        정책을 생성하기 전에 정책 상세 내용의 유효성을 확인합니다

        args:
            str policy_name : 정책번호
            list dict permissions :             권한 정책 목록

                Example:
                [
                    {
                        "effect": "Allow",
                        "targets": [
                            {
                                "product": "Server",
                                "actions": [
                                    "View*"
                                ],
                                "resourceNrns": [
                                    "*"
                                ]
                            }
                        ]
                    }
                ]

                permissions fields:
                    effect:
                        권한 허용 여부
                        - Allow

                    targets:
                        권한 대상 목록

                        product:
                            서비스 코드
                            Example:
                                Server
                                LoadBalancer
                                ObjectStorage

                        actions:
                            허용 액션 목록
                            Example:
                                ["View*"]
                                ["Change*"]
                                ["getServerInstanceList"]

                        resourceNrns:
                            리소스 NRN 목록
                            전체 허용 시:
                                ["*"]
                str description : 정책에 대한 설명(Bytes) 0~300

        Returns:
            Dict: 정책을 생성하기 전에 정책 상세 내용의 유효성을 확인합니다.

        """
        json_body = {
            'policyName' : policy_name,
            'permissions' : permissions
        }

        if description is not None:
            json_body['description'] = description
             
        return self.post(f'/api/v1/policy/validation', json_data=json_body)


    def get_policy_applied_resource(
            self,
            policy_id : str
            
            
    ) -> Dict:
        """
        정책이 할당되어 있는 리소스(서브 계정, 그룹, 역할)를 조회합니다.

        args:
            str policy_id : 정책번호
            bool with_permissions : 정책의 상세 권한 표시 여부 (true | false (기본값)) (true: 표시 false: 표시 안 함)

        Returns:
            Dict: 정책이 할당되어 있는 리소스(서브 계정, 그룹, 역할)를 조회합니다.

                
        """
        params = {}
        
             
        return self.get(f'/api/v1/policies/{policy_id}/resources', params=params)
    
    def get_policy_tag(
            self,
            policy_id : str
            
            
    ) -> Dict:
        """
        사용자 정의 정책(User Created)에 추가된 태그를 조회합니다.

        args:
            str policy_id : 정책번호
            
        Returns:
            Dict: 사용자 정의 정책(User Created)에 추가된 태그를 조회합니다.

                
        """
        params = {}
        
             
        return self.get(f'/api/v1/policies/{policy_id}/tags', params=params)
    

    """
    Cloud Subaccount Role API 클래스
    """

    def get_role_list(
            self,
            page : Optional[int] = None,
            size : Optional[int] = None,
            search_column: Optional[str] = None,
            search_word: Optional[str] = None,
            
            
    ) -> Dict:
        """
        역할 목록을 조회합니다.

        args:
            
            int page : 페이지
            int size : 페이지 사이즈
            str search_column : 검색 컬럼 (policyName)
            str search_word : 검색 키워드
            
        Returns:
            Dict: 역할 목록을 조회합니다.

                
        """
        params = {}

        if page is not None:
            params['page'] = page
        if size is not None:
            params['size'] = size
        if search_column is not None:
            params['searchColumn'] = search_column
        if search_word is not None:
            params['searchWord'] = search_word
             
        return self.get(f'/api/v1/roles', params=params)
    
    def get_role_detail(
            self,
            role_no: str
    ) -> Dict:
        """
        역할을 조회합니다.

        args:
            str role_no : 역할 아이디
            
        Returns:
            Dict: 정책 목록을 조회합니다. 
        """
        params = {}
             
        return self.get(f'/api/v1/roles/{role_no}', params=params)


    def get_role_applied_entities(
            self,
            role_no: str
    ) -> Dict:
        """
        Account 역할에 할당된 적용 대상을 조회합니다.

        args:
            str role_no : 역할 아이디
            
        Returns:
            Dict: Account 역할에 할당된 적용 대상을 조회합니다.
        """
        params = {}
             
        return self.get(f'/api/v1/roles/{role_no}/entities/account', params=params)
    
    def get_role_tag(
            self,
            role_no: str
    ) -> Dict:
        """
        역할에 추가된 태그를 조회합니다.

        args:
            str role_no : 역할 아이디
            
        Returns:
            Dict: 역할에 추가된 태그를 조회합니다.
        """
        params = {}
             
        return self.get(f'/api/v1/{role_no}/tags', params=params)
    
    def get_role_switchable_role(
            self,
            search_column : Optional[str] = None,
            search_word : Optional[str] = None
    ) -> Dict:
        """
        서브 계정에서 전환 가능한 역할 목록을 조회합니다. 서브 계정으로만 호출이 가능합니다.

        args:
            str searchColumn : 검색 컬럼 (nrn | roleDisplayName) (nrn: 역할에 대한 네이버 클라우드 플랫폼 리소스 식별 값 roleDisplayName: 역할 이름)
            str searchWord: 검색 키워드
            
        Returns:
            Dict: 서브 계정에서 전환 가능한 역할 목록을 조회합니다. 서브 계정으로만 호출이 가능합니다.
        """
        params = {}

        if search_column is not None:
            params['searchColumn'] = search_column
        if search_word is not None:
            params['searchWord'] = search_word

             
        return self.get(f'/api/v1/switchable-roles', params=params)
    


    