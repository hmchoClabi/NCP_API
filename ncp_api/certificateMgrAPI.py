from typing import Dict, List, Optional
from utils.common_rest import NCPBaseClient
from ncp_api.base import BaseNCPAPI


class CertificateMgrAPI(BaseNCPAPI):
    """
    Cloud CertificateMgr API 클래스

    """
    """
    ================================================================
    Certificate MGR V1 API
    ================================================================
    """
    def get_certificate_list(
        self,
        certificateName : Optional[str] = None,
        certificateNo : Optional[int] = None,
        instanceNo : Optional[int] = None
        
    ) -> Dict:
        """
        보유 중인 SSL 인증서를 조회합니다.

        args:
            certificateName	String	Optional	인증서 이름
            certificateNo	Integer	Optional	인증서 번호
            instanceNo	Integer	Optional	인스턴스 번호  인스턴스: 인증서를 사용 중인 연동 서비스(Global Edge, CDN+, Load Balancer)
        Returns:
            Dict: 서버 인스턴스 정보                
        """
        params = {}
        
        if certificateName is not None:
            params['certificateName'] = certificateName
        if certificateNo is not None:
            params['certificateNo'] = certificateNo
        if instanceNo is not None:
            params['instanceNo'] = instanceNo
        
        
        return self.get(f'/api/v1/certificates', params=params)