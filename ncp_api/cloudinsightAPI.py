from typing import Dict, List, Optional, Any
from utils.common_rest import NCPBaseClient
from ncp_api.base import BaseNCPAPI


class CloudInsightAPI(BaseNCPAPI):
    """
    CloudInsightAPI 클래스

    """
    """
    ================================================================
    CloudInsight Dashboard API
    ================================================================
    """
        
    def get_dashboard_list(
        self       
        
    ) -> Dict:
        
        """
        대쉬보드 목록을 조회합니다.

        args:
            None

        Returns:
            Dict: 전체 Cloud Insight 대쉬보드 목록을 조회합니다.
                
        """
        params = {}

        return self.get(f'/cw_fea/real/cw/api/chart/dashboard', params=params)
    
    def get_dashboard_widget_list(
            self,
            dashboard_id : str

    ) -> Dict:
        
        """
        대시보드의 위젯 목록을 조회합니다.

        args:
            dashboard_id : 대시보드 아이디

        Returns:
            Dict: 대시보드의 위젯 목록을 조회합니다.
                
        """
        params = {}

        return self.get(f'/cw_fea/real/cw/api/chart/dashboard/{dashboard_id}/widgets', params=params)
        
    
    
    def get_dashboard_widget_image(
        self,
        dashboard_id : str,
        widget_id : str,
        start_time : int,
        end_time : int,
        widget_resolution_mode : Optional[str] = None
    ) -> bytes:
        
        """
        대시보드의 위젯 데이터를 800x600 크기의 PNG 파일로 다운로드합니다.

        args:
            dashboard_id : 대시보드 아이디
            widget_id : 위젯 아이디
            start_time : 측정 시작 일시(밀리초) Unix Timestamp 형식
            end_time : 측정 종료 일시(밀리초) Unix Timestamp 형식
            widget_resolution_mode : 조회 주기 (AUTO (기본값) | HIGH) (AUTO: 대시보드와 동일한 주기로 조회 HIGH: 대시보드보다 짧은 주기로 상세 조회)

        Returns:
            Dict: 전체 Cloud Insight 대쉬보드 목록을 조회합니다.
        """
        params = {
            'startTime' : start_time,
            'endTime' : end_time
        }

        if widget_resolution_mode is not None:
            params['widgetResolutionMode'] = widget_resolution_mode

        return self.client.get_binary(f'/cw_fea/real/cw/api/chart/dashboard/{dashboard_id}/widgets/{widget_id}', params=params, headers={'Accept': 'image/png'})
    
    def get_dashboard_widget_list(
            self,
            dashboard_id : str

    ) -> Dict:
        
        """
        대시보드의 위젯 목록을 조회합니다.

        args:
            dashboard_id : 대시보드 아이디

        Returns:
            Dict: 대시보드의 위젯 목록을 조회합니다.
                
        """
        params = {}

        return self.get(f'/cw_fea/real/cw/api/chart/dashboard/{dashboard_id}/widgets', params=params)
    
        
    """
    ================================================================
    CloudInsight Event API
    ================================================================
    """
    def get_search_event(
            self,
            start_time: int, 
            end_time: int,
            rule_id: Optional[int] = None,
            event_id: Optional[str] = None,
            query: Optional[str] = None,
            page_no: Optional[int] = None,
            page_size: Optional[int] = None,
            only_fetch_un_close_event: Optional[bool] = None        
    ) -> Dict:
        
        """
        Cloud insight 의 Event를 조회합니다.

        args:
            int start_time: 조회시작시간(선택), 
            int end_time: 조회종료시간(선택),
            int rule_id: 이벤트룰 id,
            str event_id: 이벤트 id,
            str query: 룰이름, 메트릭이름, 리소스이름(옵션),
            int page_no: 페이지 사이즈(옵션)
            int page_size: 페이지 크기(옵션),
            bool only_fetch_un_close_event: 최근이벤트만조회(옵션)    

        Returns:
            Dict: Cloud insight의 Event를 조회합니다.
                
        """
        json_body = {
            'startTime' : start_time,
            'endTime' : end_time,
        }

        if rule_id is not None:
            json_body['ruleId'] = rule_id
        if event_id is not None:
            json_body['eventId'] = event_id
        if query is not None:
            json_body['query'] = query
        if page_no is not None:
            json_body['pageNum'] = page_no
        if page_size is not None:
            json_body['pageSize'] = page_size
        if only_fetch_un_close_event is not None:
            json_body['onlyFetchUnCloseEvent'] = only_fetch_un_close_event


        return self.post(f'/cw_fea/real/cw/api/event/search', json_data=json_body)

    def get_search_event_by_id(
            self,
            start_time: int, 
            end_time: int,
            rule_id: int,
            event_id: int,
            query: Optional[str] = None,
            page_no: Optional[int] = None,
            page_size: Optional[int] = None,
            only_fetch_un_close_event: Optional[bool] = None        
    ) -> Dict:
        
        """
        Cloud insight 의 Event id와 Rule id로 Event를 조회합니다.

        args:
            int start_time: 조회시작시간, 
            int end_time: 조회종료시간,
            int rule_id: 이벤트룰 id,
            str event_id: 이벤트 id,
            str query: 룰이름, 메트릭이름, 리소스이름(옵션),
            int page_no: 페이지 사이즈(옵션)
            int page_size: 페이지 크기(옵션),
            bool only_fetch_un_close_event: 최근이벤트만조회(옵션)

        Returns:
            Dict: Cloud insight의 Event를 조회합니다.
                
        """
        json_body = {
            'startTime' : start_time,
            'endTime' : end_time,
            'ruleId' : rule_id,
            'eventId' : event_id
        }

        if query is not None:
            json_body['query'] = query
        if page_no is not None:
            json_body['pageNum'] = page_no
        if page_size is not None:
            json_body['pageSize'] = page_size
        if only_fetch_un_close_event is not None:
            json_body['onlyFetchUnCloseEvent'] = only_fetch_un_close_event


        return self.post(f'/cw_fea/real/cw/api/event/searchById', json_data=json_body)


    def get_search_event_count_console(
            self,
            start_time: int, 
            end_time: int
    ) -> Dict:
        
        """
        Cloud insight 의 Event 발생 횟수를 조회합니다.

        args:
            int start_time: 조회시작시간, 
            int end_time: 조회종료시간

        Returns:
            Dict: 
                    closedRecords	Integer	-	처리 종료된 Event 수
                    openRecords	Integer	-	처리 대기 중인 Event 수
                    totalRecords	Integer	-	전체 Event 수
                
        """
        json_body = {
            'startTime' : start_time,
            'endTime' : end_time
        }

        return self.post(f'/cw_fea/real/cw/api/event/searchEventCountConsole', json_data=json_body)
    

    """
    ================================================================
    CloudInsight Event Rule API
    ================================================================
    """
    def get_all_monitor_group(
        self,
        prod_key : str   
    ) -> Dict:
        
        """
        서비스(상품)에 대한 전체 감시 대상 그룹 정보를 조회합니다.

        args:
            prod_key : 상품 키(cw_key) https://api.ncloud-docs.com/docs/management-cloudinsight-productinfo 참조

        Returns:
            Dict: 
                id	String	Optional	감시 대상 그룹 아이디 UpdateMonitorGrp 사용 시 필수
                prodKey	String	Required	상품 키(cw_key) Cloud Insight 지표 참조
                prodName	String	Optional	상품 이름
                groupName	String	Optional	감시 대상 그룹 이름
                groupDesc	String	Optional	감시 대상 그룹 설명
                temporaryGroup	Boolean	Optional	Rule Template 생성 여부 true | false true: 감시 대상 그룹 생성 없이 Event Rule 생성 false: Rule Template 생성
                type	String	Optional	Target Group 종류 NORMAL | ASG  NORMAL: 일반 Group  ASG: Auto Scaling Group
                monitorGroupItemList	Set<MonitorGroupItem>	Required	감시 대상 지정
        """
        params = {}

        return self.get(f'/cw_fea/real/cw/api/rule/group/monitor/{prod_key}', params=params)
    

    def get_metrics_group(
        self,
        prod_key : str,
        id : str   
    ) -> Dict:
        
        """
        서비스(상품)에 대한 특정 Rule Template(감시 항목 그룹) 정보를 조회합니다.

        args:
            prod_key : 상품 키(cw_key) https://api.ncloud-docs.com/docs/management-cloudinsight-productinfo 참조
            id : 감시 대상의 ID https://api.ncloud-docs.com/docs/management-cloudinsight-getallmonitorgrp 참조


        Returns:
            Dict: 
                createTime	Integer	-	Rule Template 생성 일시(밀리초) Unix Timestamp 형식
                domainCode	String	-	네이버 클라우드 플랫폼 도메인 코드
                groupDesc	String	-	Rule Template 설명
                groupName	String	-	Rule Template 이름
                id	String	-	Rule Template 아이디
                idDimension	String	-	Dimension 이름
                metrics	Array	-	Metric 목록: metrics
                    options	Object	-	집계 방법 "집계 주기": [집계 함수] 형태로 표시
                                        집계 주기: Min1 | Min5 | Min30 | Hour2 | Day1
                                        집계 함수: COUNT | SUM | MAX | MIN | AVG
                prodKey	String	Required	상품 키(cw_key) Cloud Insight 지표 참조
                prodType	String	-	상품 유형
                regionCode	String	-	리전 코드
                temporaryGroup	Boolean	-	Rule Template 생성 여부 true | false true: Rule Template 생성 없이 Event Rule 생성 false: Rule Template 생성
                updateTime	Integer	-	Rule Template 수정 일시(밀리초) Unix Timestamp 형식
        """
        params = {}

        return self.get(f'/cw_fea/real/cw/api/rule/group/metrics/query/{prod_key}/{id}', params=params)
    

    
    def get_metrics_group_list (
        self,
        prod_key : str   
    ) -> Dict:
        
        """
        서비스(상품)에 대한 전체 Rule Template(감시 항목 그룹) 정보를 조회합니다.

        args:
            prod_key : 상품 키(cw_key) https://api.ncloud-docs.com/docs/management-cloudinsight-productinfo 참조

        Returns:
            Dict: 
                array metricsGroups 
                    createTime	Integer	-	Rule Template 생성 일시(밀리초) Unix Timestamp 형식
                    domainCode	String	-	네이버 클라우드 플랫폼 도메인 코드
                    groupDesc	String	-	Rule Template 설명
                    groupName	String	-	Rule Template 이름
                    id	String	-	Rule Template 아이디
                    idDimension	String	-	Dimension 이름
                    metrics	Array	-	Metric 목록: metrics
                        options	Object	-	집계 방법   "집계 주기": [집계 함수] 형태로 표시
                                                집계 주기: Min1 | Min5 | Min30 | Hour2 | Day1
                                                집계 함수: COUNT | SUM | MAX | MIN | AVG
                    prodKey	String	Required	상품 키(cw_key) Cloud Insight 지표 참조
                    prodType	String	-	상품 유형
                    regionCode	String	-	리전 코드
                    temporaryGroup	Boolean	-	Rule Template 생성 여부 true | false true: Rule Template 생성 없이 Event Rule 생성 false: Rule Template 생성
                    updateTime	Integer	-	Rule Template 수정 일시(밀리초) Unix Timestamp 형식

        """
        params = {}

        return self.get(f'/cw_fea/real/cw/api/rule/group/metrics/query/{prod_key}', params=params)

    def get_monitor_group  (
        self,
        prod_key : str,
        id: str   
    ) -> Dict:
        
        """
        서비스(상품)에 대한 특정 감시 대상 그룹 정보를 조회합니다.

        args:
            prod_key : 상품 키(cw_key) https://api.ncloud-docs.com/docs/management-cloudinsight-productinfo 참조
            id : 감시 대상의 ID https://api.ncloud-docs.com/docs/management-cloudinsight-getallmonitorgrp 참조

        Returns:
            Dict: 
                id	String	Optional	감시 대상 그룹 아이디   UpdateMonitorGrp 사용 시 필수
                prodKey	String	Required	상품 키(cw_key)  Cloud Insight 지표 참조
                prodName	String	Optional	상품 이름
                groupName	String	Optional	감시 대상 그룹 이름
                groupDesc	String	Optional	감시 대상 그룹 설명
                temporaryGroup	Boolean	Optional	Rule Template 생성 여부 true | false true: 감시 대상 그룹 생성 없이 Event Rule 생성 false: Rule Template 생성
                type	String	Optional	Target Group 종류 NORMAL | ASG NORMAL: 일반 Group ASG: Auto Scaling Group
                monitorGroupItemList	Set<MonitorGroupItem>	Required	감시 대상 지정
        """
        params = {}

        return self.get(f'/cw_fea/real/cw/api/rule/group/monitor/{prod_key}/{id}', params=params)
    
    def get_notification_recipient_list  (
        self
    ) -> Dict:
        
        """
        서비스(상품)에 대한 특정 감시 대상 그룹 정보를 조회합니다.

        args:
            prod_key : 상품 키(cw_key) https://api.ncloud-docs.com/docs/management-cloudinsight-productinfo 참조
            id : 감시 대상의 ID https://api.ncloud-docs.com/docs/management-cloudinsight-getallmonitorgrp 참조

        Returns:
            Dict: 
                personalNotification	Boolean	-	통보 대상 유형 true | false  true: 통보 대상자 false: 통보 대상자 그룹
        """
        params = {}

        return self.get(f'/cw_fea/real/cw/api/rule/notify/groups', params=params)
    
    def get_rule_group   (
        self,
        prod_key : str,
        id : str
    ) -> Dict:
        
        """
        특정 Event Rule을 조회합니다.

        args:
            prod_key : 상품 키(cw_key) https://api.ncloud-docs.com/docs/management-cloudinsight-productinfo 참조
            id : 감시 대상의 ID https://api.ncloud-docs.com/docs/management-cloudinsight-getallmonitorgrp 참조

        Returns:
            Dict: 
                id	String	-	Event Rule ID
                prodKey	String	-	상품의 cw_key
                groupName	String	-	Event Rule 이름
                groupDesc	String	-	Event Rule 설명
                domainCode	String	-	도메인 코드
                regionCode	String	-	리전 코드
                monitorGroups	List<MonitorGrpDto>	-	감시 대상 그룹
                metricsGroups	List<MetricsGroupDto>	-	감시 항목 그룹
                productName	String	-	상품의 이름
                recipientNotifications	List<RecipientNotification>	-	통보 대상 그룹 여러 개 입력 가능
                asgGroupOptions	List<AsgGroupOptions>	-	Auto Scaling Group 설정 정보
                asgGroupOptions.id	String	-	Auto Scaling Group 아이디
                asgGroupOptions.reminderTime	Integer	-	리마인드 알림 주기(분)
                asgGroupOptions.type	String	-	이벤트 액션 타입
                asgGroupOptions.updateTime	Integer	-	업데이트 시간(밀리초)
                asgPolicys	List<AsgPolicy>	-	오토 스케일링 그룹 정책 여러 개 입력 가능
                createTime	long	-	Event Rule 생성 시간(밀리초)
                updateTime	long	-	Event Rule 수정 시간(밀리초)
                status		-	상태 OK | VIOLATED | INSUFFICIENT
                ruleVersion		-	룰 버전
                cfTriggers	Set<String>	-	Cloud Functions Trigger
                cfTriggersOptions	List<cfTriggersOptions>	-	Cloud Functions Trigger 설정 정보
                cfTriggersOptions.name	String	-	Cloud Functions Trigger 이름
                cfTriggersOptions.enableNotiWhenEventClose	Boolean	-	이벤트 종료 시 알림 활성화 여부 true | false  true: 활성화  false: 비활성화
                cfTriggersOptions.reminderTime	Integer	-	리마인드 알림 주기(분)
                cfTriggersOptions.type	String	-	이벤트 액션 타입
                cfTriggersOptions.updateTime	Integer	-	업데이트 시간(밀리초)
                suspendRuleItems	Set<SuspendRuleItemDto>	-	Event Rule 중 비활성화할 목록 설정
        """
        params = {}

        return self.get(f'/cw_fea/real/cw/api/rule/group/ruleGrp/query/{prod_key}/{id}', params=params)
    
    def get_rule_group_by_metric_group_ids(
            self,
            prod_key : str,
            metric_group_ids : List[str]
    ) -> Dict:
        
        """
        Rule Template(감시 항목 그룹)과 관련된 Event Rule을 조회합니다.

        args:
            prod_key : 상품 키(cw_key) https://api.ncloud-docs.com/docs/management-cloudinsight-productinfo 참조 
            metric_group_ids : Rule Template 아이디 목록 GetMetricsGroupList 참조 2개 이상 조회 시 쉼표(,)로 구분
        Returns:
            Dict: 
                    id	String	-	Event Rule ID
                    prodKey	String	-	상품의 cw_key
                    groupName	String	-	Event Rule 이름
                    groupDesc	String	-	Event Rule 설명
                    domainCode	String	-	도메인 코드
                    regionCode	String	-	리전 코드
                    monitorGroups	List<MonitorGrpDto>	-	감시 대상 그룹
                    metricsGroups	List<MetricsGroupDto>	-	감시 항목 그룹
                    productName	String	-	상품의 이름
                    recipientNotifications	List<RecipientNotification>	-	통보 대상 그룹 여러 개 입력 가능
                    asgGroupOptions	List<AsgGroupOptions>	-	Auto Scaling Group 설정 정보
                    asgGroupOptions.id	String	-	Auto Scaling Group 아이디
                    asgGroupOptions.reminderTime	Integer	-	리마인드 알림 주기(분)
                    asgGroupOptions.type	String	-	이벤트 액션 타입
                    asgGroupOptions.updateTime	Integer	-	업데이트 시간(밀리초)
                    asgPolicys	List<AsgPolicy>	-	오토 스케일링 그룹 정책 여러 개 입력 가능
                    createTime	long	-	Event Rule 생성 시간(밀리초)
                    updateTime	long	-	Event Rule 수정 시간(밀리초) status		-	상태  OK | VIOLATED | INSUFFICIENT
                    ruleVersion		-	룰 버전
                    cfTriggers	Set<String>	-	Cloud Functions Trigger
                    cfTriggersOptions	List<cfTriggersOptions>	-	Cloud Functions Trigger 설정 정보
                    cfTriggersOptions.name	String	-	Cloud Functions Trigger 이름
                    cfTriggersOptions.enableNotiWhenEventClose	Boolean	-	이벤트 종료 시 알림 활성화 여부 true | false  true: 활성화 false: 비활성화
                    cfTriggersOptions.reminderTime	Integer	-	리마인드 알림 주기(분)
                    cfTriggersOptions.type	String	-	이벤트 액션 타입
                    cfTriggersOptions.updateTime	Integer	-	업데이트 시간(밀리초)
                    suspendRuleItems	Set<SuspendRuleItemDto>	-	Event Rule 중 비활성화할 목록 설정
                
        """
        params = {
            'prodKey' : prod_key
        }
        

        return self.post(f'/cw_fea/real/cw/api/rule/group/metric/group/related', json_data=metric_group_ids, params=params)
    
    def get_rule_group_by_monitor_group_ids(
            self,
            prod_key : str,
            monitor_group_ids : List[str]
    ) -> Dict:
        
        """
        감시 대상 그룹과 관련된 Event Rule을 조회합니다.

        args:
            prod_key : 상품 키(cw_key) https://api.ncloud-docs.com/docs/management-cloudinsight-productinfo 참조 
            metric_group_ids : 감시 대상 그룹 아이디 목록 GetAllMonitorGrp 참조 2개 이상 시 쉼표(,)로 구분
        
        Returns:
            Dict: 
                id	String	-	Event Rule ID
                prodKey	String	-	상품의 cw_key
                groupName	String	-	Event Rule 이름
                groupDesc	String	-	Event Rule 설명
                domainCode	String	-	도메인 코드
                regionCode	String	-	리전 코드
                monitorGroups	List<MonitorGrpDto>	-	감시 대상 그룹
                metricsGroups	List<MetricsGroupDto>	-	감시 항목 그룹
                productName	String	-	상품의 이름
                recipientNotifications	List<RecipientNotification>	-	통보 대상 그룹 여러 개 입력 가능
                asgGroupOptions	List<AsgGroupOptions>	-	Auto Scaling Group 설정 정보
                asgGroupOptions.id	String	-	Auto Scaling Group 아이디
                asgGroupOptions.reminderTime	Integer	-	리마인드 알림 주기(분)
                asgGroupOptions.type	String	-	이벤트 액션 타입
                asgGroupOptions.updateTime	Integer	-	업데이트 시간(밀리초)
                asgPolicys	List<AsgPolicy>	-	오토 스케일링 그룹 정책 여러 개 입력 가능
                createTime	long	-	Event Rule 생성 시간(밀리초)
                updateTime	long	-	Event Rule 수정 시간(밀리초) status		-	상태  OK | VIOLATED | INSUFFICIENT
                ruleVersion		-	룰 버전
                cfTriggers	Set<String>	-	Cloud Functions Trigger
                cfTriggersOptions	List<cfTriggersOptions>	-	Cloud Functions Trigger 설정 정보
                cfTriggersOptions.name	String	-	Cloud Functions Trigger 이름
                cfTriggersOptions.enableNotiWhenEventClose	Boolean	-	이벤트 종료 시 알림 활성화 여부 true | false  true: 활성화 false: 비활성화
                cfTriggersOptions.reminderTime	Integer	-	리마인드 알림 주기(분)
                cfTriggersOptions.type	String	-	이벤트 액션 타입
                cfTriggersOptions.updateTime	Integer	-	업데이트 시간(밀리초)
                suspendRuleItems	Set<SuspendRuleItemDto>	-	Event Rule 중 비활성화할 목록 설정
                
        """
        params = {
            'prodKey' : prod_key
        }
        

        return self.post(f'/cw_fea/real/cw/api/rule/group/monitor/group/related', json_data=monitor_group_ids, params=params)


    def get_rule_group_list(
            self,
            prod_key : str,
            page_no : int,
            page_size : int,
            search : Optional[str] = None
    ) -> Dict:
        
        """
        전체 Event Rule 목록을 조회합니다.

        args:
            prod_key	String	Required	상품 키(cw_key) Cloud Insight 지표 참조
            page_size	Integer	Required	페이지 출력 수
            page_no	Integer	Required	페이지 번호
            search	String	Optional	조회 키워드
        
        Returns:
            Dict: 
                id	String	-	Event Rule ID
                prodKey	String	-	상품의 cw_key
                groupName	String	-	Event Rule 이름
                groupDesc	String	-	Event Rule 설명
                domainCode	String	-	도메인 코드
                regionCode	String	-	리전 코드
                monitorGroups	List<MonitorGrpDto>	-	감시 대상 그룹
                metricsGroups	List<MetricsGroupDto>	-	감시 항목 그룹
                productName	String	-	상품의 이름
                recipientNotifications	List<RecipientNotification>	-	통보 대상 그룹 여러 개 입력 가능
                asgGroupOptions	List<AsgGroupOptions>	-	Auto Scaling Group 설정 정보
                asgGroupOptions.id	String	-	Auto Scaling Group 아이디
                asgGroupOptions.reminderTime	Integer	-	리마인드 알림 주기(분)
                asgGroupOptions.type	String	-	이벤트 액션 타입
                asgGroupOptions.updateTime	Integer	-	업데이트 시간(밀리초)
                asgPolicys	List<AsgPolicy>	-	오토 스케일링 그룹 정책 여러 개 입력 가능
                createTime	long	-	Event Rule 생성 시간(밀리초)
                updateTime	long	-	Event Rule 수정 시간(밀리초) 
                status		-	상태  OK | VIOLATED | INSUFFICIENT
                ruleVersion		-	룰 버전
                cfTriggers	Set<String>	-	Cloud Functions Trigger
                cfTriggersOptions	List<cfTriggersOptions>	-	Cloud Functions Trigger 설정 정보
                cfTriggersOptions.name	String	-	Cloud Functions Trigger 이름
                cfTriggersOptions.enableNotiWhenEventClose	Boolean	-	이벤트 종료 시 알림 활성화 여부 true | false  true: 활성화 false: 비활성화
                cfTriggersOptions.reminderTime	Integer	-	리마인드 알림 주기(분)
                cfTriggersOptions.type	String	-	이벤트 액션 타입
                cfTriggersOptions.updateTime	Integer	-	업데이트 시간(밀리초)
                suspendRuleItems	Set<SuspendRuleItemDto>	-	Event Rule 중 비활성화할 목록 설정
        """
        json_body = {
            'prodKey' : prod_key,
            'pageNum' : page_no,
            'pageSize' : page_size,
        }

        if search is not None:
            json_body['search'] = search
        

        return self.post(f'/cw_fea/real/cw/api/rule/group/ruleGrp/query', json_data=json_body)
    
    def get_search_metric_list(
            self,
            prod_key : str,
            query : Optional[str] = None,
            id_dimensions : Optional[List[str]] = None,
            dim_values : Optional[List[dict[str, str]]] = None,
            dimensions_selected_list : Optional[List[dict[str,Any]]] = None
    ) -> Dict[str, Any]:
        
        """
        감시 대상 그룹에서 Metric 목록을 조회합니다. 메트릭 조회 Metric 조회

        args:
            prod_key	String	Required	상품의 cw_key
            query	String	Optional	키워드
            idDimensions	List	Optional	조회하려는 idDimension
            dimValues	List<DimensionDto>	Optional	조회하려는 Dimension 정보 ( str dim : str val )
            dimensionsSelectedList	List<DimensionsSelected>	Optional	특정 Dimension value로 검색 ( str name : list[str] values )
        
        Returns:
            Dict: 
                metrics	Array	-	Metric 목록: metrics
                    dataType	String	-	데이터 타입
                    desc	String	-	Metric 설명
                    dimensions	Array	-	Dimension 목록: dimensions
                        dim	String	-	Dimension 이름
                        val	String	-	Dimension 값
                    idDimension	String	-	Dimension 이름
                    metric	String	-	Metric 이름
                    options	Object	-	집계 방법 "집계 주기": [집계 함수] 형태로 표시
                                        집계 주기: Min1 | Min5 | Min30 | Hour2 | Day1
                                        집계 함수: COUNT | SUM | MAX | MIN | AVG
                    prodKey	String	Required	상품 키(cw_key) Cloud Insight 지표 참조
                    unit	String	-	단위
                prodKey	String	Required	상품 키(cw_key) Cloud Insight 지표 참조
        """
        json_body = {
            'prodKey' : prod_key
        }
        if query is not None:
            json_body['query'] = query
        if id_dimensions is not None:
            json_body['idDimensions'] = id_dimensions
        if dim_values is not None:
            json_body['dimValues'] = dim_values
        if dimensions_selected_list is not None:
            json_body['dimensionsSelectedList'] = dimensions_selected_list           
        
      
        return self.post(f'/cw_fea/real/cw/api/rule/group/metric/search', json_data=json_body)
    


    
    """
    ================================================================
    CloudInsight Schema API
    ================================================================
    """
    def get_extended_status_metric_list(
            self,
            prod_key : str,
            servers : list[str]
    ) -> Dict:
        
        """
        인스턴스의 Extended Metric 수집 설정 상태를 조회합니다. 상세 모니터링 켜졌는지.

        args:
            prod_key	String	Required	상품 키(cw_key) Cloud Insight 지표 참조
            servers	Array	Required	인스턴스 아이디 목록
        
        Returns:
            Dict: 
                enabled	Boolean	-	Extended Metric 수집 설정 여부 true | false  true: 설정  false: 설정 해제
                instanceId	String	-	인스턴스 아이디
        """
        json_body = {
            'prodKey' : prod_key,
            'servers' : servers
        }
             
        
      
        return self.post(f'/cw_fea/real/cw/api/schema/extended/status', json_data=json_body)
    
    def get_product_schema(
            self,
            prod_name : str,
            cw_key : Optional[str] = None
    ) -> Dict:
        
        """
        사용자 정의 스키마를 조회합니다.

        args:
            prodName	Strng	Required	상품 이름  Cloud Insight 지표 참조  사용자 정의 스키마: Custom/으로 시작
            cw_key	String	Optional	상품 키(cw_key)   Cloud Insight 지표 참조

        Returns:
            Dict: 
                cw_key	String	-	상품 키(cw_key)  Cloud Insight 지표 참조
                fields	Array	-	사용자 정의 스키마
                prodName	String	-	상품 이름   Cloud Insight 지표 참조
                useCustomResource	Boolean	Optional	사용자 정의 리소스 사용 여부   true | false (기본값)  true: 사용  false: 사용 안 함
        """
        params = {
            'prodName' : prod_name
        }

        if cw_key is not None:
            params['cw_key'] = cw_key
        
        return self.get(f'/cw_fea/real/cw/api/schema', params=params)
    
    def get_system_schema_key_list(
            self
    ) -> Dict:
        
        """
        Cloud Insight에서 활용할 수 있도록 성능/운영 지표를 제공하는 네이버 클라우드 플랫폼 서비스(상품) 정보를 조회합니다.   상품키 조회 , cw_key 조회회
        
        args:
            None

        Returns:
            Dict: 
                cw_key	String	-	상품 키(cw_key)  Cloud Insight 지표 참조
                prodName	String	-	상품 이름   Cloud Insight 지표 참조
        """
        params = {}

        
        
        return self.get(f'/cw_fea/real/cw/api/schema/system/list', params=params)
    

    """
    ================================================================
    CloudInsight Custom Schema API
    ================================================================
    """
    def get_all_custom_resource(
            self,
            resource_type_id : Optional[str] = None,
            query : Optional[str] = None
    ) -> Dict:
        
        """
        전체 사용자 리소스를 조회합니다.
        
        args:
            resource_type_id	String	Optional	사용자 리소스 유형 아이디   resourceData 데이터 타입 인증을 위해 사용되는 값    정의한 데이터 타입의 사용자 리소스만 조회   DEFAULT (기본값)
            query	String	Optional	조회 키워드     resourceTypeId에서 정의한 데이터 타입의 사용자 리소스만 조회


        Returns:
            Dict: 
                resourceData	Object	-	사용자 리소스 데이터
                resourceId	String	-	사용자 리소스 아이디
                resourceName	String	-	사용자 리소스 이름
                resourceTypeId	String	-	사용자 리소스 유형 아이디
        """
        params = {}

        if resource_type_id is not None:
            params['resourceTypeId'] = resource_type_id
        if query is not None:
            params['query'] = query
        
        
        return self.get(f'/cw_fea/real/cw/api/custom/resource/list', params=params)

    def get_custom_resource(
            self,
            resource_id : str
    ) -> Dict:
        
        """
        특정 사용자 리소스를 조회합니다.
        
        args:
            resource_id	String	Required	사용자 리소스 아이디 GetAllCustomResource 참조

        Returns:
            Dict: 
                resourceData	Object	-	사용자 리소스 데이터    
                resourceId	String	-	사용자 리소스 아이디
                resourceName	String	-	사용자 리소스 이름
                resourceTypeId	String	Optional	사용자 리소스 유형 아이디   resourceData 데이터 타입 인증을 위해 사용되는 값 정의한 데이터 타입의 사용자 리소스만 조회    DEFAULT (기본값)
        """
        params = {}

        
        
        return self.get(f'/cw_fea/real/cw/api/custom/resource/{resource_id}', params=params)
    
    """
    ================================================================
    CloudInsight PlannedMaintenance API
    ================================================================
    """
    def get_planned_maintenance_list(
            self,
            page_no : int,
            page_size : int,
            from_time : Optional[int] = None,
            to_time : Optional[int] = None,
            time_type : Optional[str] = None,
            resource_id : Optional[str] = None,
            product_key : Optional[str] = None,

    ) -> Dict:
        
        """
        전체 유지 보수 일정 목록을 조회합니다. 조회 방식은 두 가지를 지원하며, 선택하여 호출해야 합니다.
            시간 범위로 조회: 요청 쿼리 파라미터 from, to, timeType 사용
            리소스 아이디로 조회: 요청 쿼리 파라미터 resourceId, productKey 사용
            조회 방식:
            1. 시간 범위 조회: from, to, timeType
            2. 리소스 기준 조회: resourceId, productKey
        
        args:
            from	Integer	Conditional	조회 시작 일시 Unix timestamp 형식 시간 범위로 조회 시 사용
            to	Integer	Conditional	조회 종료 일시 Unix timestamp 형식 시간 범위로 조회 시 사용
            timeType	String	Conditional	조회 기준 startTime | endTime   startTime: 시작 시간 기준    endTime: 종료 시간 기준준  시간 범위로 조회 시 사용
            resourceId	String	Conditional	리소스 아이디   GetAllCustomResource 참조   리소스 아이디로 조회 시 사용
            productKey	String	Conditional	상품 키(cw_key) Cloud Insight 지표 참조 리소스 아이디로 조회 시 사용
            pageNum	Integer	Required	페이지 번호 1~N
            pageSize	Integer	Required	페이지 출력 수  1~N

        Returns:
            Dict: 
                desc	String	Optional	설명
                dimensions	Map<String, Set>	Required	Dimension을 JSON으로 명시   
                    key: cw_key <예시> 460438474722512896   cw_key는 dimensions 객체의 key로 사용됨
                    value: 리소스 Dimension 목록
                    <예시> {"dimensions": "123456": [{ "instanceNo": "1111", "type": "svr" }]}
                    위 예시에서 "123456"이 cw_key에 해당함
                startTime	Long	Required	Planned Maintenance 시작 시간(밀리초)
                endTime	Long	Required	Planned Maintenance 종료 시간(밀리초)
                title	String	Required	Planned Maintenance 제목
        """
        params = {
            "pageNum": page_no,
            "pageSize": page_size
        }

        # 시간 범위 조회 여부
        is_time_range_query = (
            from_time is not None or
            to_time is not None or
            time_type is not None
        )

        # 리소스 기준 조회 여부
        is_resource_query = (
            resource_id is not None or
            product_key is not None
        )

        # 둘 다 섞이면 안 됨
        if is_time_range_query and is_resource_query:
            raise ValueError(
                "시간 범위 조회(from_time, to_time, time_type)와 "
                "리소스 기준 조회(resource_id, product_key)는 동시에 사용할 수 없습니다."
            )

        # 둘 다 없으면 안 됨
        if not is_time_range_query and not is_resource_query:
            raise ValueError(
                "시간 범위 조회(from_time, to_time, time_type) 또는 "
                "리소스 기준 조회(resource_id, product_key) 중 하나를 선택해야 합니다."
            )

        # 시간 범위 조회
        if is_time_range_query:
            if from_time is None or to_time is None or time_type is None:
                raise ValueError(
                    "시간 범위 조회 시 from_time, to_time, time_type은 모두 필수입니다."
                )

            if time_type not in ("startTime", "endTime"):
                raise ValueError("time_type은 'startTime' 또는 'endTime'이어야 합니다.")

            params["from"] = from_time
            params["to"] = to_time
            params["timeType"] = time_type

        # 리소스 기준 조회
        if is_resource_query:
            if resource_id is None or product_key is None:
                raise ValueError(
                    "리소스 기준 조회 시 resource_id, product_key는 모두 필수입니다."
                )

            params["resourceId"] = resource_id
            params["productKey"] = product_key
             
        return self.get(f'/cw_fea/real/cw/api/planned-maintenances', params=params)
    
    def get_planned_maintenance_detail_by_id(
            self,
            id: str
    ) -> Dict:
        
        """
        유지 보수 일정 아이디를 지정하여 특정 유지 보수 일정을 조회합니다.
        
        args:
            id	String	Required	유지 보수 일정 아이디   GetPlannedMaintenanceList 참조

        Returns:
            Dict: 
                desc	String	Optional	설명    
                dimensions	Map<String, Set>	Required	Dimension을 JSON으로 명시   
                    key: cw_key <예시> 460438474722512896   
                    value: 리소스 Dimension 목록    
                    cw_key는 dimensions 객체의 key로 사용됨 
                    <예시> {"dimensions": "123456": [{ "instanceNo": "1111", "type": "svr" }]}  위 예시에서 "123456"이 cw_key에 해당함
                startTime	Long	Required	Planned Maintenance 시작 시간(밀리초)
                endTime	Long	Required	Planned Maintenance 종료 시간(밀리초)
                title	String	Required	Planned Maintenance 제목

        """
        params = {}       
        
        return self.get(f'/cw_fea/real/cw/api/planned-maintenances/{id}', params=params)
    
    """
    ================================================================
    CloudInsight Plugin API
    ================================================================
    """
    def get_all_file_plugin (
            self
            
    ) -> Dict:
        
        """
        전체 서버의 File Plugin 설정을 조회합니다.
        
        args:
            None

        Returns:
            Dict: 
                configList	Array	-	파일 경로 목록
                instanceNo	String	-	서버 인스턴스 번호
                nrn	String	-	네이버 클라우드 플랫폼 리소스 식별 값
                type	String	-	서버 유형
        """
        params = {}       
        
        return self.get(f'/cw_server/real/api/plugin/file', params=params)
    
    def get_all_port_plugin(
        self
            
    ) -> Dict:
        
        """
        전체 서버의 Port Plugin 설정을 조회합니다.
        
        args:
            None

        Returns:
            Dict: 
                instanceNo	String	-	서버 인스턴스 번호
                nrn	String	-	네이버 클라우드 플랫폼 리소스 식별 값
                portList	Array	-	포트 번호 목록
                type	String	-	서버 유형
        """
        params = {}       
        
        return self.get(f'/cw_server/real/api/plugin/port', params=params)
    
    def get_all_process_plugin(
        self
            
    ) -> Dict:
        
        """
        전체 서버의 Process Plugin 설정을 조회합니다.
        
        args:
            None

        Returns:
            Dict: 
                configList	Array	-	프로세스 이름 목록
                instanceNo	String	-	서버 인스턴스 번호
                nrn	String	-	네이버 클라우드 플랫폼 리소스 식별 값
                type	String	-	서버 유형
        """
        params = {}       
        
        return self.get(f'/cw_server/real/api/plugin/process', params=params)
    
    def get_file_plugin (
            self,
            instance_no : str
            
    ) -> Dict:
        
        """
        전체 서버의 File Plugin 설정을 조회합니다.
        
        args:
            instanceNo	String	Required	서버 인스턴스 번호 1개만 입력 가능
        Returns:
            Dict: 
                configList	Array	-	파일 경로 목록
                instanceNo	String	-	서버 인스턴스 번호
                nrn	String	-	네이버 클라우드 플랫폼 리소스 식별 값
                type	String	-	서버 유형
        """
        params = {}       
        
        return self.get(f'/cw_server/real/api/plugin/file/instanceNo/{instance_no}', params=params)

    def get_port_plugin (
            self,
            instance_no : str
            
    ) -> Dict:
        
        """
        전체 서버의 File Plugin 설정을 조회합니다.
        
        args:
            instanceNo	String	Required	서버 인스턴스 번호 1개만 입력 가능
        Returns:
            Dict: 
                instanceNo	String	-	서버 인스턴스 번호
                nrn	String	-	네이버 클라우드 플랫폼 리소스 식별 값
                portList	Array	-	포트 번호 목록
                type	String	-	서버 유형
        """
        params = {}       
        
        return self.get(f'/cw_server/real/api/plugin/port/instanceNo/{instance_no}', params=params)
    
    def get_process_plugin (
            self,
            instance_no : str
            
    ) -> Dict:
        
        """
        특정 서버의 Process Plugin 설정을 조회합니다.
        
        args:
            instanceNo	String	Required	서버 인스턴스 번호 1개만 입력 가능
        Returns:
            Dict: 
                configList	Array	-	프로세스 이름 목록
                instanceNo	String	-	서버 인스턴스 번호
                nrn	String	-	네이버 클라우드 플랫폼 리소스 식별 값
                type	String	-	서버 유형
        """
        params = {}       
        
        return self.get(f'/cw_server/real/api/plugin/process/instanceNo/{instance_no}', params=params)
    
    """
    ================================================================
    CloudInsight Server API
    ================================================================
    """

    def get_servers_top (
            self,
            query : str,
            prod  : Optional[str] = None
            
    ) -> Dict:
        
        """
        특정 서버의 Process Plugin 설정을 조회합니다.
        
        args:
            query	String	Required	Metric 이름
                    avg_cpu_used_rto | mem_usert | avg_fs_usert
                        avg_cpu_used_rto: CPU 사용률 평균
                        mem_usert: 메모리 사용률
                        avg_fs_usert: 파일 시스템 사용률 평균
            prod	String	Optional	서버가 속한 환경    VPC (기본값)| Classic   VPC: VPC 환경  Classic: Classic 환경
        
        Returns:
            Dict: 
                avg_cpu_user_rto	String	-	CPU 사용자 비율 평균(%)
                hostName	String	-	호스트 이름
                instanceNo	String	-	호스트 인스턴스 번호
                avg_cpu_used_rto	Number	-	CPU 사용률 평균(%)
                avg_fs_usert	Number	-	파일 시스템 사용률 평균(%)
                mem_usert	Number	-	메모리 사용률(%)
        """
        params = {
            'query' : query
        }

        if prod is not None:
            params['prod'] = prod
        
        return self.post(f'/cw_fea/real/cw/api/servers/top', params=params)
    
    """
    ================================================================
    CloudInsight data API
    ================================================================
    """
    def get_query_data (
            self,
            cw_key : str,
            metric : str,
            dimensions : dict[str,str],
            time_start : Optional[int] = None,
            time_end : Optional[int] = None,
            product_name : Optional[str] = None,
            interval : Optional[str] = None,
            aggregation : Optional[str] = None,
            query_aggregation : Optional[str] = None
    ) -> Dict:
        
        """
        Cloud Insight에서 수집한 time-series 데이터를 조회합니다.
        
        args:
            timeStart	long	Optional	조회 시작 시간(밀리초)
            timeEnd	long	Optional	조회 종료 시간(밀리초)
            productName	String	Optional	상품명
            cw_key	String	Required	상품의 cw_key
            metric	String	Required	조회하려는 Metric 이름
            interval	Interval	Optional	조회하려는 데이터의 집계 주기   Min1(기본값) | Min5 | Min30 | Hour2 | Day1
            aggregation	Calculation	Optional	조회하려는 데이터의 집계 함수   COUNT | SUM | MAX | MIN | AVG (기본값)
            queryAggregation	QueryAggregation	Optional	쿼리 기준이 충분하지 않을 때 쿼리 결과를 처리하는 방법  COUNT | SUM | MAX | MIN | AVG (기본값)
            dimensions	Map<String, String>	Required	조회하려는 Dimension을 JSON으로 명시
        
        Returns:
            Dict: 
                data	Array	-	조회 결과   데이터 포인트(Unix Timestamp 형식), 데이터 값 형태로 표시
        """
        json_body = {
            'cw_key' : cw_key,
            'metric' : metric,
            'dimensions' : dimensions
        }

        if time_start is not None:
            json_body['timeStart'] = time_start
        if time_end is not None:
            json_body['timeEnd'] = time_end
        if product_name is not None:
            json_body['productName'] = product_name
        if interval is not None:
            json_body['interval'] = interval
        if aggregation is not None:
            json_body['aggregation'] = aggregation
        if query_aggregation is not None:
            json_body['queryAggregation'] = query_aggregation
        
        return self.post(f'/cw_fea/real/cw/api/data/query', json_data=json_body)
    
    def get_query_data_multiple (
        self,
        time_start: int,
        time_end: int,
        metric_info_list: list[dict[str,Any]]
    ) -> Dict:
        
        """
        Cloud Insight에서 수집한 여러 개의 time-series 데이터를 조회합니다.
        
        args:
            time_start	Integer	Required	조회 시작 일시(밀리초) Unix Timestamp 형식
            time_end	Integer	Required	조회 종료 일시(밀리초) Unix Timestamp 형식
            metric_info_list	Array	Required	조회 조건 1회 호출에 최대 20개의 조건 조회 가능
                    prodKey	String	Required	상품의 cw_key
                    metric	String	Required	조회하려는 Metric 이름  
                    interval	Interval	Required	조회하려는 데이터의 집계 주기 Min1 | Min5 | Min30 | Hour2 | Day1
                    aggregation	Calculation	Optional	조회하려는 데이터의 집계 함수 COUNT | SUM (기본값) | MAX | MIN | AVG
                    queryAggregation	QueryAggregation	Optional	쿼리 기준이 충분하지 않을 때 쿼리 결과를 처리하는 방법  COUNT | SUM (기본값) | MAX | MIN | AVG
                    dimensions	Map<String, String>	Required	조회하려는 Dimension을 JSON으로 명시
        
        Returns:
            Dict: 
                aggregation	String	-	집계 함수  COUNT | SUM | MAX | MIN | AVG
                dimensions	Object	-	Dimension 정보
                dimensions.instanceNo	String	-	인스턴스 번호
                dps	Array	-	조회 결과 데이터 포인트(Unix Timestamp 형식), 데이터 값 형태로 표시 interval	String	-	집계 주기 Min1 | Min5 | Min30 | Hour2 | Day1
                metric	String	-	Metric 이름
                productName	String	-	상품 이름 Cloud Insight 지표 참조
        """
        json_body = {
            'timeStart' : time_start,
            'timeEnd' : time_end,
            'metricInfoList' : metric_info_list
        }
        
        return self.post(f'/cw_fea/real/cw/api/data/query/multiple', json_data=json_body)
    

    def get_query_widget_data_preview  (
        self,
        period_start: int,
        period_end: int,
        metrics_info: list[dict[str,Any]]
    ) -> list[dict[str, Any]]:
        
        """
        Metric 정보를 통한 Preview Chart 조회입니다.
        
        args:
            periodStart	long	Required	조회 시작 시간(밀리초) 현재 시간으로부터 1시간 이전(기본값)
            periodEnd	long	Required	조회 종료 시간(밀리초) 현재 시간(기본값)
            metricsInfo	List<WidgetMetricInfoDto>	Required	데이터 조회를 위한 Metric 정보
                    WidgetMetricInfoDto
                        displayName	String	-	Widget에서 보여지는 Metric의 이름
                        prodKey	String	-	상품의 cw_key
                        prodName	String	-	상품의 이름
                        metric	String	-	조회하려는 Metric 이름
                        dimensions	Map<String, String>	-	조회하려는 데이터의 Dimension 이름 key/value로 입력 가능
                        statistic	Calculation	-	조회하려는 집계 함수 COUNT | SUM | MAX | MIN | AVG
                        period	Interval	-	조회하려는 집계 주기 Min1 | Min5 | Min30 | Hour2 | Day1
                        color	String	-	위젯에서 보여지는 차트의 색깔
                        data	JSONArray	-	조회된 결과
        
        Returns:
            Dict: 
                color	String	-	차트 색
                data	Array	-	조회 결과 데이터 포인트(Unix Timestamp 형식), 데이터 값 형태로 표시
                dimensions	Object	-	Dimension 정보
                dimensions.instanceNo	String	-	인스턴스 번호
                dimensions.name	String	-	Dimension 이름
                dimensions.type	String	-	Dimension 유형
                displayName	String	-	위젯에 노출되는 Metric 이름
                idDimension	String	-	Dimension 이름
                metric	String	-	Metric 이름
                period	String	-	집계 주기 Min1 | Min5 | Min30 | Hour2 | Day1
                prodKey	String	-	상품 키(cw_key) Cloud Insight 지표 참조
                prodName	String	-	상품 이름 Cloud Insight 지표 참조
                resourceName	String	-	리소스 이름
                statistic	String	-	집계 함수 COUNT | SUM | MAX | MIN | AVG

        """
        json_body = {
            'periodStart' : period_start,
            'periodEnd' : period_end,
            'metricsInfo' : metrics_info
        }
        
        return self.post(f'/cw_fea/real/cw/api/data/chart/preview', json_data=json_body)
    