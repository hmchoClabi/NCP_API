from typing import Dict, List, Optional, Any
from utils.common_rest import NCPBaseClient


class CloudActivityTracerAPI:
    """
    CloudActivityTracerAPI 클래스

    """
    
    def __init__(self, client: NCPBaseClient):
        """
         초기화합니다.
        
        Args:
            client: NCPBaseClient 인스턴스
        """
        self.client = client
    """
    ================================================================
    CloudActivityTracerAPI Dashboard API
    ================================================================
    """
        
    def get_activity_list (
        self,
        fromEventTime : Optional[int] = None,
        toEventTime : Optional[int] = None,
        nrn : Optional[str] = None,
        page : Optional[str] = None,
        size : Optional[str] = None,
        
    ) -> Dict:
        
        """
        리소스 작업 내역을 조회합니다. 리소스는 사용자가 네이버 클라우드 플랫폼에서 생성한 자원의 단위입니다. 리소스는 식별이 가능하도록 NRN(Ncloud Resource Names)이라는 고유한 키 값으로 구분하여 관리하기 때문에 NRN을 사용하여 호출 시 특정 리소스에 대한 작업 내역을 조회할 수 있습니다.

        args:
            fromEventTime	Integer	Optional	조회 기간 시작 일시(밀리초) Unix Timestamp 형식 조회 일시로부터 30일 전 (기본값)
            toEventTime	Integer	Optional	조회 기간 종료 일시(밀리초) Unix Timestamp 형식 조회 일시 (기본값)
            nrn	String	Optional	네이버 클라우드 플랫폼 리소스 식별 값
            page	Integer	Optional	페이지 번호 0~N (기본값: 0)
            size	Integer	Optional	페이지 출력 수 100 이하 (기본값: 20)


        Returns:
            Dict: 
                page	Integer	-	페이지 번호
                size	Integer	-	페이지 출력 수
                itemCount	Integer	-	응답 결과 수
                hasMore	Boolean	-	추가 페이지 존재 여부   true | false    true: 존재  false: 존재 안 함
                items	Array	-	응답 결과: items
                    historyId	String	-	리소스 작업 내역 아이디
                    nrn	String	-	네이버 클라우드 플랫폼 리소스 식별 값
                    eventTime	Integer	-	작업 변경 일시(밀리초)ul>   Unix Timestamp 형식
                    platformType	String	-	플랫폼 구분 BOTH | VPC | Classic BOTH: 플랫폼 공통 환경 VPC: VPC 환경 Classic: Classic 환경
                    productName	String	-	리소스의 서비스 코드
                    productDisplayName	String	-	리소스의 서비스 이름
                    regionCode	String	-	리소스의 리전 코드
                    regionDispalyName	String	-	리소스의 리전 이름
                    resourceType	String	-	리소스 유형
                    resourceId	String	-	리소스 아이디
                    resourceName	String	-	리소스 이름
                    actionDisplayName	String	-	작업 이름
                    actionResultType	String	-	작업 결과 SUCCESS | FAIL SUCCESS: 성공 FAIL: 실패
                    actionUserType	String	-	작업자 유형 Customer | Sub Customer: 메인 계정 Sub: 서브 계정
                    actionSubAccountNo	Integer	-	서브 계정 회원 번호 actionUserType이 Sub인 경우 표시
                    sourceType	String	-	작업을 요청한 클라이언트 유형 API | CONSOLE | PORTAL | SYSTEM
                    sourceIp	String	-	작업을 요청한 클라이언트 IP 주소 sourceType이 CONSOLE이거나 PORTAL인 경우 표시
                    productData	Object	-	리소스 상세 정보 각 필드 정보: 리소스별 API 가이드 참조

                
        """
        json_body = {}

        if fromEventTime is not None:
            json_body['fromEventTime'] = fromEventTime
        if toEventTime is not None:
            json_body['toEventTime'] = toEventTime
        if nrn is not None:
            json_body['nrn'] = nrn
        if page is not None:
            json_body['page'] = page
        if size is not None:
            json_body['size'] = size

        return self.client.post(f'/api/v1/activities', json_data=json_body)
    
