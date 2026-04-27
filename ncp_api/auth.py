"""
네이버 클라우드 플랫폼 API 인증 모듈

NCP API 인증을 처리하는 모듈입니다.
HMAC-SHA256 알고리즘을 사용하여 서명을 생성합니다.
"""

import hmac
import hashlib
import base64
from datetime import datetime
from typing import Dict, Optional
from urllib.parse import quote


class NCPAuth:
    """
    네이버 클라우드 플랫폼 API 인증 클래스
    
    Access Key와 Secret Key를 사용하여 API 요청에 필요한 서명을 생성합니다.
    """
    
    def __init__(self, access_key: str, secret_key: str):
        """
        NCP 인증 객체를 초기화합니다.
        
        Args:
            access_key: NCP Access Key
            secret_key: NCP Secret Key
        """
        self.access_key = access_key
        self.secret_key = secret_key
    
    def generate_signature(
        self,
        method: str,
        uri: str,
        timestamp: Optional[str] = None,
        query_string: Optional[str] = None
    ) -> str:
        """
        API 요청을 위한 서명을 생성합니다.
        
        Args:
            method: HTTP 메서드 (GET, POST, PUT, PATCH, DELETE 등)
            uri: 요청 URI (엔드포인트 경로)
            timestamp: 타임스탬프 (기본값: 현재 시간)
            query_string: 쿼리 스트링 (선택사항)
        
        Returns:
            str: 생성된 서명 문자열
        """
        if timestamp is None:
            timestamp = str(int(datetime.now().timestamp() * 1000))
        
        # 서명 생성 문자열 구성
        message = f"{method} {uri}\n{timestamp}\n{self.access_key}"
        
        if query_string:
            message = f"{method} {uri}?{query_string}\n{timestamp}\n{self.access_key}"
        
        # HMAC-SHA256으로 서명 생성
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        # Base64 인코딩
        signature_base64 = base64.b64encode(signature).decode('utf-8')
        
        return signature_base64
    
    def get_auth_headers(
        self,
        method: str,
        uri: str,
        timestamp: Optional[str] = None,
        query_string: Optional[str] = None
    ) -> Dict[str, str]:
        """
        인증 헤더를 생성합니다.
        
        Args:
            method: HTTP 메서드
            uri: 요청 URI
            timestamp: 타임스탬프 (기본값: 현재 시간)
            query_string: 쿼리 스트링 (선택사항)
        
        Returns:
            Dict[str, str]: 인증 헤더 딕셔너리
        """
        if timestamp is None:
            timestamp = str(int(datetime.now().timestamp() * 1000))
        
        signature = self.generate_signature(method, uri, timestamp, query_string)
        
        return {
            'x-ncp-apigw-timestamp': timestamp,
            'x-ncp-iam-access-key': self.access_key,
            'x-ncp-apigw-signature-v2': signature
        }
    
    def get_timestamp(self) -> str:
        """
        현재 타임스탬프를 반환합니다.
        
        Returns:
            str: 밀리초 단위 타임스탬프 문자열
        """
        return str(int(datetime.now().timestamp() * 1000))

