from typing import Dict, List, Optional, Any
from utils.common_rest import NCPBaseClient


class SecurityMonitoringAPI:
    """
    SecurityMonitoringAPI 클래스

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
    SecurityMonitoringAPI
    백신
    ================================================================
    """

    def get_anti_virus_list (
        self,
        startDateTime: int,
        endDateTime: int,
        page: int,
        countPerPage: int,
        order: Optional[str] = None,
        regionCode: Optional[str] = None,
        zoneName : Optional[str] = None,
        infectedServerIp : Optional[str] = None,
        detectionPath : Optional[str] = None,
        malwareType : Optional[str] = None,       
    ) -> Dict:

        """
        Anti-Virus 서비스 사용 중에 발생한 보안 이벤트 목록을 조회합니다.

        args:
            startDateTime	Long	Required	보안 이벤트 조회 시작 시간  Unix timestamp 형식 <예시> 1720540427000
            endDateTime	Long	Required	보안 이벤트 조회 종료 시간 Unix timestamp 형식 <예시> 1720540427000
            page	Integer	Required	페이지 번호
            countPerPage	Integer	Required	페이지당 노출 개수
            order	String	Optional	이벤트 탐지 시간 정렬 순서 asc | desc (기본값) asc: 오름차순 desc: 내림차순
            regionCode	String	Optional	리전 코드 KR | KRS  KR: 수도권 KRS: 남부권
            zoneName	String	Optional	존 구분     KR-1
            infectedServerIp	String	Optional	보안 이벤트가 탐지된 서버 IP 주소
            detectionPath	String	Optional	보안 이벤트가 탐지된 상세 경로
            malwareType	String	Optional	탐지된 악성 코드의 유형


        Returns:
            Dict: 
                returnCode	Integer	-	요청에 대한 처리 결과 코드
                returnMessage	String	-	요청에 대한 처리 결과 메시지
                totalRows	Integer	-	조회된 목록의 총 개수
                page	Integer	-	요청 페이지 번호
                antiVirusDataList	Array	-	Anti-Virus 보안 이벤트 목록: antiVirusDataList


                
        """
        json_body = {
            "startDateTime": startDateTime,
            "endDateTime": endDateTime,
            "page": page,
            "countPerPage": countPerPage
        }

        if order is not None:
            json_body['order'] = order
        if regionCode is not None:
            json_body['regionCode'] = regionCode
        if zoneName is not None:
            json_body['zoneName'] = zoneName
        if infectedServerIp is not None:
            json_body['infectedServerIp'] = infectedServerIp
        if detectionPath is not None:
            json_body['detectionPath'] = detectionPath
        if malwareType is not None:
            json_body['malwareType'] = malwareType

        return self.client.post(f'/vsecuritymonitoring/v1/getAVList', json_data=json_body)
    


    def get_ddos_list (
        self,
        startDateTime: int,
        endDateTime: int,
        page: int,
        countPerPage: int,
        order: Optional[str] = None,
        regionCode: Optional[str] = None,
        zoneName : Optional[str] = None,
        attackIp : Optional[str] = None,
        targetIp : Optional[str] = None
        
    ) -> Dict:

        """
        Anti-DDoS (Anti-Distributed Denial of Service) 서비스 사용 중에 발생한 보안 이벤트 목록을 조회합니다.

        args:
            startDateTime	Long	Required	보안 이벤트 조회 시작 시간 Unix timestamp 형식 <예시> 1720540427000
            endDateTime	Long	Required	보안 이벤트 조회 종료 시간 Unix timestamp 형식 <예시> 1720540427000
            page	Integer	Required	페이지 번호
            countPerPage	Integer	Required	페이지당 노출 개수
            order	String	Optional	이벤트 탐지 시간 정렬 순서 asc | desc (기본값) asc: 오름차순 desc: 내림차순
            regionCode	String	Optional	리전 코드 KR | KRS KR: 수도권 KRS: 남부권  KR: 수도권 KRS: 남부권
            zoneName	String	Optional	존 구분 KR-1
            attackIp	String	Optional	공격자 IP 주소
            targetIp	String	Optional	공격 대상 IP 주소

        Returns:
            Dict: 
                returnCode	Integer	-	요청에 대한 처리 결과 코드
                ddosDataList	Array	-	Anti-DDoS 보안 이벤트 목록: ddosDataList
                    ticketId	String	-	보안 이벤트에 부여된 고유 번호
                    date	String	-	보안 이벤트의 탐지 시간 Unix timestamp 형식
                    product	String	-	서비스 구분 DDOS | DDOS_V2 DDOS: Classic 환경 DDOS_V2: VPC 환경
                    reportType	String	-	보고 구분
                    attackerIp	String	-	공격자 IP 주소
                    targetIp	String	-	공격 대상 IP 주소
                    attackType	String	-	탐지된 공격 유형
                    region	String	-	리전
                    zoneName	String	-	존 구분 KR-1
                    platForm	String	-	플랫폼 구분 CLASSIC | VPC
                    vpcName	String	-	VPC 이름
                returnMessage	String	-	요청에 대한 처리 결과 메시지
                totalRows	Integer	-	조회된 목록의 총 개수
                page	Integer	-	요청 페이지 번호
                ddosDataList	Array	-	Anti-DDoS 보안 이벤트 목록: ddosDataList       
"""
        json_body = {
            "startDateTime": startDateTime,
            "endDateTime": endDateTime,
            "page": page,
            "countPerPage": countPerPage
        }

        if order is not None:
            json_body['order'] = order
        if regionCode is not None:
            json_body['regionCode'] = regionCode
        if zoneName is not None:
            json_body['zoneName'] = zoneName
        if attackIp is not None:
            json_body['attackIp'] = attackIp
        if targetIp is not None:
            json_body['targetIp'] = targetIp

        return self.client.post(f'/vsecuritymonitoring/v1/getDDoSList', json_data=json_body)

    def get_ddos_event_detail (
        self,
        ticketId: str
        
    ) -> Dict:

        """
        Anti-DDoS (Anti-Distributed Denial of Service) 서비스 사용 중에 발생한 보안 이벤트의 상세 정보를 조회합니다.

        args:
            ticketId	String	Required	조회할 DDoS 보안 이벤트의 고유 번호 getDDoSList 참조


        Returns:
            Dict: 
                returnCode	Integer	-	요청에 대한 처리 결과 코드
                lbName	String	-	보안 이벤트가 탐지된 로드밸런서 이름
                returnMessage	String	-	요청에 대한 처리 결과 메시지
                report	String	-	보안 이벤트의 상세 정보
                lbDomainName	String	-	보안 이벤트가 탐지된 로드밸런서의 DNS 이름
                lbInstanceNo	String	-	보안 이벤트가 탐지된 로드밸런서의 인스턴스 번호
        """
        json_body = {
            "ticketId" : ticketId
        }

        

        return self.client.post(f'/vsecuritymonitoring/v1/getDDoSEventDetail', json_data=json_body)
    
    def get_ids_list(
        self, 
        startDateTime: int,
        endDateTime: int,
        page: int,
        countPerPage: int,
        order: Optional[str] = None,
        regionCode: Optional[str] = None,
        zoneName : Optional[str] = None,
        attackType : Optional[str] = None,
        attackIp : Optional[str] = None,
        targetIp : Optional[str] = None
    ) -> Dict:
        """
        IDS (Intrusion Detection System) 서비스 사용 중에 발생한 보안 이벤트 목록을 조회합니다.

        args:
            ticketId	String	Required	조회할 DDoS 보안 이벤트의 고유 번호 getDDoSList 참조


        Returns:
            Dict: 
                returnCode	Integer	-	요청에 대한 처리 결과 코드
                lbName	String	-	보안 이벤트가 탐지된 로드밸런서 이름
                returnMessage	String	-	요청에 대한 처리 결과 메시지
                report	String	-	보안 이벤트의 상세 정보
                lbDomainName	String	-	보안 이벤트가 탐지된 로드밸런서의 DNS 이름
                lbInstanceNo	String	-	보안 이벤트가 탐지된 로드밸런서의 인스턴스 번호
        """
        json_body = {
            "startDateTime": startDateTime,
            "endDateTime": endDateTime,
            "page": page,
            "countPerPage": countPerPage
        }
        if order is not None:
            json_body['order'] = order
        if regionCode is not None:
            json_body['regionCode'] = regionCode
        if zoneName is not None:
            json_body['zoneName'] = zoneName
        if attackType is not None:
            json_body['attackType'] = attackType
        if attackIp is not None:
            json_body['attackIp'] = attackIp
        if targetIp is not None:
            json_body['targetIp'] = targetIp

        return self.client.post(f'/vsecuritymonitoring/v1/getIDSList', json_data=json_body)
    
    def get_ids_event_detail (
        self,
        ticketId: str
        
    ) -> Dict:

        """
        IDS (Intrusion Detection System) 서비스 사용 중에 발생한 보안 이벤트의 상세 정보를 조회합니다.

        args:
            ticketId	String	Required	조회할 DDoS 보안 이벤트의 고유 번호 getDDoSList 참조


        Returns:
            Dict: 
                returnCode	Integer	-	요청에 대한 처리 결과 코드
                lbName	String	-	보안 이벤트가 탐지된 로드밸런서 이름
                returnMessage	String	-	요청에 대한 처리 결과 메시지
                report	String	-	보안 이벤트의 상세 정보
                lbDomainName	String	-	보안 이벤트가 탐지된 로드밸런서의 DNS 이름
                lbInstanceNo	String	-	보안 이벤트가 탐지된 로드밸런서의 인스턴스 번호
        """
        json_body = {
            "ticketId" : ticketId
        }

        

        return self.client.post(f'/vsecuritymonitoring/v1/getIDSEventDetail', json_data=json_body)
    
    def get_ips_list(
        self, 
        startDateTime: int,
        endDateTime: int,
        page: int,
        countPerPage: int,
        order: Optional[str] = None,
        regionCode: Optional[str] = None,
        zoneName : Optional[str] = None,
        eventNm : Optional[str] = None,
        attackIp : Optional[str] = None,
        targetIp : Optional[str] = None,
        attackType : Optional[str] = None,
        protocol : Optional[str] = None,
        
        
    ) -> Dict:
        """
        IDS (Intrusion Detection System) 서비스 사용 중에 발생한 보안 이벤트 목록을 조회합니다.

        args:
            startDateTime	Long	Required	보안 이벤트 조회 시작 시간 Unix Timestamp 형식 <예시> 1720540427000
            endDateTime	Long	Required	보안 이벤트 조회 종료 시간 Unix Timestamp 형식 <예시> 1720540427000
            page	Integer	Required	페이지 번호
            countPerPage	Integer	Required	페이지당 노출 개수
            order	String	Optional	이벤트 탐지 시간 정렬 순서 asc | desc (기본값) asc: 오름차순 desc: 내림차순
            regionCode	String	Optional	리전 코드 KR | DEN | JPN | SGN | USWN KR: 한국 DEN: 독일 JPN: 일본 SGN: 싱가포르 USWN: 미국
            zoneName	String	Optional	존 구분 KR-1 | KR-2
            eventNm	String	Optional	탐지된 이벤트의 이름
            attackIp	String	Optional	공격자 IP 주소
            targetIp	String	Optional	공격 대상 IP 주소
            attackType	String	Optional	탐지된 공격 유형  Classic 환경에서만 사용 가능
            protocol	String	Optional	공격 프로토콜 VPC 환경에서만 사용 가능


        Returns:
            Dict: 
                returnCode	Integer	-	요청에 대한 처리 결과 코드
                ipsDataList	Array	-	IPS 보안 이벤트 목록: ipsDataList
                    ticketId	String	-	보안 이벤트에 부여된 고유 번호
                    date	String	-	보안 이벤트의 탐지 시간 Unix Timestamp 형식
                    product	String	-	서비스 구분 IPS | IPS_V2 IPS: Classic 환경 IPS_V2: VPC 환경
                    eventNm	String	-	탐지된 보안 이벤트의 이름
                    attackType	String	-	탐지된 공격 유형
                    attackerIp	String	-	공격자 IP 주소
                    attackerPort	String	-	공격자의 포트 번호
                    targetIp	String	-	공격 대상 IP 주소
                    targetPort	String	-	공격 대상의 포트 번호
                    protocol	String	-	공격 프로토콜
                    detect	String	-	보안 이벤트 탐지 건수
                    region	String	-	리전
                    zoneName	String	-	존 구분 KR-1 | KR-2 
                    platForm	String	-	플랫폼 구분 CLASSIC | VPC
                    vpcName	String	-	VPC 이름
                returnMessage	String	-	요청에 대한 처리 결과 메시지
                totalRows	Integer	-	조회된 목록의 총 개수
                page	Integer	-	요청 페이지 번호
        """
        json_body = {
            "startDateTime": startDateTime,
            "endDateTime": endDateTime,
            "page": page,
            "countPerPage": countPerPage
        }
        if order is not None:
            json_body['order'] = order
        if regionCode is not None:
            json_body['regionCode'] = regionCode
        if zoneName is not None:
            json_body['zoneName'] = zoneName
        if eventNm is not None:
            json_body['eventNm'] = eventNm
        if attackIp is not None:
            json_body['attackIp'] = attackIp
        if targetIp is not None:
            json_body['targetIp'] = targetIp
        if attackType is not None:
            json_body['attackType'] = attackType
        if protocol is not None:
            json_body['protocol'] = protocol
        
        

        return self.client.post(f'/vsecuritymonitoring/v1/getIPSList', json_data=json_body)
    

    def get_waf_list(
        self, 
        startDateTime: int,
        endDateTime: int,
        page: int,
        countPerPage: int,
        order: Optional[str] = None,
        regionCode: Optional[str] = None,
        zoneName : Optional[str] = None,
        attackType : Optional[str] = None,
        eventNm : Optional[str] = None,
        attackIp : Optional[str] = None,
        targetIp : Optional[str] = None,
        
        
        
        
    ) -> Dict:
        """
        IDS (Intrusion Detection System) 서비스 사용 중에 발생한 보안 이벤트 목록을 조회합니다.

        args:
            startDateTime	Long	Required	보안 이벤트 조회 시작 시간 Unix Timestamp 형식 <예시> 1720540427000
            endDateTime	Long	Required	보안 이벤트 조회 종료 시간 Unix Timestamp 형식 <예시> 1720540427000
            page	Integer	Required	페이지 번호
            countPerPage	Integer	Required	페이지당 노출 개수
            order	String	Optional	이벤트 탐지 시간 정렬 순서 asc | desc (기본값) asc: 오름차순 desc: 내림차순
            regionCode	String	Optional	리전 코드 KR | DEN | JPN | SGN | USWN KR: 한국 DEN: 독일 JPN: 일본 SGN: 싱가포르 USWN: 미국
            zoneName	String	Optional	존 구분 KR-1 | KR-2
            attackType	String	Optional	탐지된 공격 유형  
            eventNm	String	Optional	탐지된 이벤트의 이름
            attackIp	String	Optional	공격자 IP 주소
            targetIp	String	Optional	공격 대상 IP 주소
            
            


        Returns:
            Dict: 
                returnCode	Integer	-	요청에 대한 처리 결과 코드
                wafDataList	Array	-	WAF 보안 이벤트 목록: wafDataList
                    ticketId	String	-	보안 이벤트에 부여된 고유 번호
                    date	String	-	보안 이벤트의 탐지 시간(Unix timestamp)
                    product	String	-	서비스 구분 WAF | WAF_V2  WAF: Classic 환경 WAF_V2: VPC 환경
                    eventNm	String	-	탐지된 보안 이벤트의 이름
                    attackType	String	-	탐지된 공격 유형
                    attackerIp	String	-	공격자 IP 주소
                    attackerPort	String	-	공격자의 포트 번호
                    targetIp	String	-	공격 대상 IP 주소
                    targetPort	String	-	공격 대상의 포트 번호 
                    region	String	-	리전
                    zoneName	String	-	존 구분 KR-1 | KR-2
                    platForm	String	-	플랫폼 구분 CLASSIC | VPC
                    vpcName	String	-	VPC 이름
                returnMessage	String	-	요청에 대한 처리 결과 메시지
                totalRows	Integer	-	조회된 목록의 총 개수
                page	Integer	-	요청 페이지 번호
        """
        json_body = {
            "startDateTime": startDateTime,
            "endDateTime": endDateTime,
            "page": page,
            "countPerPage": countPerPage
        }
        if order is not None:
            json_body['order'] = order
        if regionCode is not None:
            json_body['regionCode'] = regionCode
        if zoneName is not None:
            json_body['zoneName'] = zoneName
        if attackType is not None:
            json_body['attackType'] = attackType
        if eventNm is not None:
            json_body['eventNm'] = eventNm
        if attackIp is not None:
            json_body['attackIp'] = attackIp
        if targetIp is not None:
            json_body['targetIp'] = targetIp
                

        return self.client.post(f'/vsecuritymonitoring/v1/getWAFList', json_data=json_body)
     

    