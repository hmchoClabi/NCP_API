from typing import Dict, List, Optional
from ncp_api.base import BaseNCPAPI


class WebServiceMonitorAPI(BaseNCPAPI):
    """
    Web Service Monitor 클래스

    """

    ENDPOINT_KEY = "webservicemonitor"
    """
    ================================================================
    웹서비스 모니터 관련 API
    ================================================================
    """
        
    def get_wms_monitor_list(
        self       
    ) -> Dict:
        
        """
        전체 WMS 모니터링 서비스 목록을 조회합니다.

        args:
            None
        Returns:
            Dict: 전체 WMS 모니터링 서비스 목록을 조회합니다.
                
        """
        params = {}

        return self.client.get(f'/api/v1/scenarios', params=params)

    def get_wms_monitor_result(
            self,
            scenario_id : str,
            from_time : int,
            to_time : int,
            type : int,
            result_status = Optional[str],
            location_type_codes = Optional[str]
  

    ) -> Dict:
        
        """
        모니터링 서비스의 결과를 조회합니다.

        args:
            str scenario_id : 시나리오 아이디
            int from_time : 시작시간 unix_timestamp
            int to_time : 종료시간 unix_timestamp
            str type : 모니터링 결과 데이터 유형 ( RAW | MIN5 | MIN30 | MIN30 ) (RAW: 전체 MIN5: 5분 집계 MIN30: 30분 집계 HOUR2: 2시간 집계 DAY1: 1일 집계)
            str result_status : 모니터링 결과 ( SUCCESS | ERROR ) ( SUCCESS: 성공 ERROR: 실패 )
            str locationTypeCodes : 모니터링 측정 Agent가 위치한 국가 ( KR | USW | JP | SG | DE ) ( KR: 한국 USW: 미국(서부) JP: 일본 SG: 싱가포르 DE: 독일 2개 이상 선택 시 쉼표(,)로 구분)

        Returns:
            Dict: 전체 WMS 모니터링 서비스 목록을 조회합니다.
                
        """    

        params = {}

        if from_time is not None:
            params['from'] = from_time
        if to_time is not None:
            params['to'] = to_time
        if type is not None:
            params['type'] = type
        if result_status is not None:
            params['resultStatus'] = result_status
        if location_type_codes is not None:
            params['locationTypeCodes'] = location_type_codes

        return self.client.get(f'/api/v1/scenarios/{scenario_id}/results', params=params)
    
    
    def get_wms_monitor_result_detail(
            self,
            scenario_id : str,
            result_id : str,
            type : str
    ) -> Dict:
        
        """
        모니터링 서비스의 결과를 조회합니다.

        args:
            str scenario_id : 시나리오 아이디디
            str resultId : 	모니터링 결과 아이디 
            str type :  모니터링 결과 데이터 유형 ( RAW | MIN5 | MIN30 | MIN30 ) ( RAW: 전체 | MIN5: 5분 집계 | MIN30: 30분 집계 | HOUR2: 2시간 집계 | DAY1: 1일 집계 )

        Returns:
            Dict: 전체 WMS 모니터링 서비스 목록을 조회합니다.
                
        """    
        
        params = {}

        return self.client.get(f'/api/v1/scenarios/{scenario_id}/results/{result_id}', params=params)
    
    def get_wms_monitor_detail(
            self,
            scenario_id : str
    ) -> Dict:
        
        """
        모니터링 서비스의 상세 정보를 조회합니다.

        args:
            str scenario_id : 시나리오 아이디

        Returns:
            Dict: 모니터링 서비스의 상세 정보를 조회합니다.
        """    
        
        params = {}

        return self.client.get(f'/api/v1/scenarios/{scenario_id}', params=params)