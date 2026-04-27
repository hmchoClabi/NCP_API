"""
RESTful API 공용 클라이언트 모듈

모든 HTTP 메서드와 파라미터 타입을 지원하는 범용 API 클라이언트입니다.
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List, Union
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
import requests

from ncp_api.auth import NCPAuth
from config.settings import API_TIMEOUT, API_RETRY_COUNT


logger = logging.getLogger(__name__)


class NCPBaseClient:
    """
    네이버 클라우드 플랫폼 RESTful API 공용 클라이언트
    
    모든 HTTP 메서드(GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS)를 지원하며,
    다양한 파라미터 타입(string, int, float, list, dict, array)을 처리할 수 있습니다.
    """
    
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        base_url: str,
        timeout: int = API_TIMEOUT,
        retry_count: int = API_RETRY_COUNT
    ):
        """
        API 클라이언트를 초기화합니다.
        
        Args:
            access_key: NCP Access Key
            secret_key: NCP Secret Key
            base_url: API 기본 URL
            timeout: 요청 타임아웃 (초)
            retry_count: 재시도 횟수
        """
        self.auth = NCPAuth(access_key, secret_key)
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.retry_count = retry_count
        self.session = requests.Session()
    
    def _prepare_params(self, params: Optional[Union[Dict, List]]) -> str:
        """
        파라미터를 쿼리 스트링으로 변환합니다.
        리스트와 딕셔너리 타입을 지원합니다.
        
        Args:
            params: 파라미터 딕셔너리 또는 리스트
        
        Returns:
            str: 쿼리 스트링
        """
        if not params:
            return ''
        
        # 리스트 타입인 경우 처리
        if isinstance(params, list):
            # 리스트를 딕셔너리로 변환 (인덱스 기반)
            params = {str(i): v for i, v in enumerate(params)}
        
        # 딕셔너리 타입 처리
        if isinstance(params, dict):
            # 중첩된 딕셔너리나 리스트를 JSON 문자열로 변환
            processed_params = {}
                # NCP 도메인 여부 판단
            is_ncp_api = (
                'ntruss.com' in self.base_url or
                'gov-ntruss.com' in self.base_url
            )

            for key, value in params.items():
                # ✅ NCP 전용: list 타입을 param.1=value 형태로 변환
                if is_ncp_api and isinstance(value, list):
                    for idx, v in enumerate(value, 1):
                        processed_params[f"{key}.{idx}"] = str(v)
                elif isinstance(value, (dict, list)):
                    # 복잡한 타입은 JSON 문자열로 변환
                    processed_params[key] = json.dumps(value, ensure_ascii=False)
                elif isinstance(value, bool):
                    # 불린 타입은 소문자 문자열로 변환
                    processed_params[key] = str(value).lower()
                else:
                    processed_params[key] = str(value)
            
            return urlencode(processed_params)
        
        return ''
    
    def _prepare_headers(
        self,
        method: str,
        uri: str,
        custom_headers: Optional[Dict[str, str]] = None,
        query_string: Optional[str] = None
    ) -> Dict[str, str]:
        """
        요청 헤더를 준비합니다.
        기본 헤더와 인증 헤더, 커스텀 헤더를 병합합니다.
        
        Args:
            method: HTTP 메서드
            uri: 요청 URI
            custom_headers: 커스텀 헤더 딕셔너리
            query_string: 쿼리 스트링
        
        Returns:
            Dict[str, str]: 병합된 헤더 딕셔너리
        """
        # 기본 헤더
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        # 인증 헤더 추가
        auth_headers = self.auth.get_auth_headers(method, uri, query_string=query_string)
        headers.update(auth_headers)
        
        # 커스텀 헤더 추가 (우선순위가 높음)
        if custom_headers:
            headers.update(custom_headers)
        
        return headers
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Union[Dict, List]] = None,
        data: Optional[Union[Dict, List, str, bytes]] = None,
        json_data: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        files: Optional[Dict] = None,
        timeout: Optional[int] = None
    ) -> requests.Response:
        """
        HTTP 요청을 실행합니다.
        
        Args:
            method: HTTP 메서드 (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS)
            endpoint: API 엔드포인트 경로
            params: 쿼리 파라미터 (dict, list 지원)
            data: 요청 본문 데이터 (form 데이터, 문자열, 바이트)
            json_data: JSON 요청 본문 데이터 (dict, list 지원)
            headers: 커스텀 헤더
            files: 파일 업로드용 파일 딕셔너리
            timeout: 요청 타임아웃 (초)
        
        Returns:
            requests.Response: HTTP 응답 객체
        
        Raises:
            requests.RequestException: 요청 실패 시
        """

        if endpoint.startswith('http') or endpoint.startswith('https'):
            url = endpoint
            endpoint_for_auth = url
        else:
            # 엔드포인트 정규화
            endpoint = endpoint.lstrip('/')
            url = f"{self.base_url}/{endpoint}"
            endpoint_for_auth = url
        
        # 파라미터 처리
        query_string = self._prepare_params(params)
        if query_string:
            url = f"{url}?{query_string}"
        
        # URI 추출 (인증용)
        parsed_url = urlparse(url)
        uri = parsed_url.path
        if parsed_url.query:
            uri = f"{uri}?{parsed_url.query}"
        
        # 헤더 준비
        request_headers = self._prepare_headers(
            method,
            uri,
            custom_headers=headers,
            query_string=query_string if not parsed_url.query else None
        )
        
        # 타임아웃 설정
        request_timeout = timeout if timeout is not None else self.timeout
        
        # 요청 데이터 준비
        request_kwargs = {
            'headers': request_headers,
            'timeout': request_timeout
        }
        
        # JSON 데이터 처리
        if json_data is not None:
            request_kwargs['json'] = json_data
            # JSON 요청 시 Content-Type이 이미 설정되어 있음
        
        # Form 데이터 처리
        elif data is not None and not files:
            if isinstance(data, (dict, list)):
                # 딕셔너리나 리스트인 경우 JSON으로 처리
                request_kwargs['json'] = data
            else:
                # 문자열이나 바이트인 경우 그대로 전송
                request_kwargs['data'] = data
        
        # 파일 업로드 처리
        if files:
            # 파일 업로드 시 Content-Type을 multipart/form-data로 설정
            if 'Content-Type' in request_headers:
                del request_headers['Content-Type']
            request_kwargs['files'] = files
            if data and isinstance(data, dict):
                request_kwargs['data'] = data
        
        # 로깅 (상세 디버깅)
        logger.info(f"[API Request] {method} {url}")
        logger.debug(f"  - Full URL: {url}")
        logger.debug(f"  - Headers: {request_headers}")
        if json_data:
            logger.info(f"  - Request Body (JSON): {json_data}")
            logger.debug(f"  - Request Body (JSON, full): {json.dumps(json_data, ensure_ascii=False, indent=2)}")
        elif data:
            logger.info(f"  - Request Body (Data): {data}")
            logger.debug(f"  - Request Body (Data, full): {data}")
        if params:
            logger.debug(f"  - Query Params: {params}")
        
        # 요청 실행 (재시도 로직 포함)
        last_exception = None
        for attempt in range(self.retry_count):
            try:
                response = self.session.request(method, url, **request_kwargs)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                last_exception = e
                if attempt < self.retry_count - 1:
                    wait_time = 2 ** attempt  # 지수 백오프
                    logger.warning(f"Request failed (attempt {attempt + 1}/{self.retry_count}): {e}")
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Request failed after {self.retry_count} attempts: {e}")
        
        raise last_exception
    
    def request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Union[Dict, List]] = None,
        data: Optional[Union[Dict, List, str, bytes]] = None,
        json_data: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        files: Optional[Dict] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        API 요청을 실행하고 응답을 반환합니다.
        
        모든 HTTP 메서드를 지원하며, 다양한 파라미터 타입을 처리할 수 있습니다.
        
        Args:
            method: HTTP 메서드 (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS)
            endpoint: API 엔드포인트 경로
            params: 쿼리 파라미터 (dict, list 지원)
            data: 요청 본문 데이터 (form 데이터, 문자열, 바이트)
            json_data: JSON 요청 본문 데이터 (dict, list 지원)
            headers: 커스텀 헤더
            files: 파일 업로드용 파일 딕셔너리
            timeout: 요청 타임아웃 (초)
        
        Returns:
            Dict[str, Any]: JSON 응답을 파싱한 딕셔너리
        
        Raises:
            requests.RequestException: 요청 실패 시
            json.JSONDecodeError: JSON 파싱 실패 시
        
        Examples:
            # GET 요청
            response = client.request('GET', '/vserver/v2/getServerInstanceList')
            
            # POST 요청 (JSON)
            response = client.request('POST', '/vserver/v2/createServerInstances', 
                                    json_data={'serverName': 'test'})
            
            # PUT 요청 (파라미터)
            response = client.request('PUT', '/vserver/v2/changeServerInstanceSpec',
                                    params={'serverInstanceNo': '123'})
            
            # PATCH 요청 (커스텀 헤더)
            response = client.request('PATCH', '/vserver/v2/updateServer',
                                    json_data={'name': 'new_name'},
                                    headers={'X-Custom-Header': 'value'})
        """
        response = self._make_request(
            method=method,
            endpoint=endpoint,
            params=params,
            data=data,
            json_data=json_data,
            headers=headers,
            files=files,
            timeout=timeout
        )
        
        # 응답 로깅 (상세 디버깅)
        logger.info(f"[API Response] Status: {response.status_code}")
        logger.debug(f"  - Response Headers: {dict(response.headers)}")
        logger.debug(f"  - Response URL: {response.url}")
        
        # JSON 응답 파싱
        try:
            json_response = response.json()
            # 응답 구조 디버깅
            # Cloud Insight API는 리스트를 반환할 수 있음
            if isinstance(json_response, list):
                logger.info(f"  - Response Type: List (length: {len(json_response)})")
                if len(json_response) > 0:
                    logger.info(f"  - First Item Type: {type(json_response[0])}")
                    if isinstance(json_response[0], (list, tuple)):
                        logger.info(f"  - First Item: {json_response[0]}")
                    elif isinstance(json_response[0], dict):
                        logger.info(f"  - First Item Keys: {list(json_response[0].keys())}")
                        logger.info(f"  - First Item: {json_response[0]}")
                logger.debug(f"  - Full Response (List): {json.dumps(json_response, ensure_ascii=False, indent=2)[:1000]}...")
            elif isinstance(json_response, dict):
                logger.info(f"  - Response Type: Dict")
                logger.info(f"  - Response Keys: {list(json_response.keys())}")
                response_str = json.dumps(json_response, ensure_ascii=False, indent=2)
                if len(response_str) > 1000:
                    logger.info(f"  - Response Body (first 1000 chars): {response_str[:1000]}...")
                    logger.debug(f"  - Full Response Body: {response_str}")
                else:
                    logger.info(f"  - Response Body: {response_str}")
            else:
                logger.info(f"  - Response Type: {type(json_response)}")
                logger.info(f"  - Response: {json_response}")
            return json_response
        except json.JSONDecodeError as e:
            # JSON이 아닌 경우 텍스트 반환
            logger.error(f"JSON 파싱 실패: {e}")
            logger.error(f"Response Text: {response.text[:500]}")
            return {'text': response.text, 'status_code': response.status_code, 'error': 'json_decode_error'}
    
    # 편의 메서드들
    def get(
        self,
        endpoint: str,
        params: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """GET 요청을 실행합니다."""
        return self.request('GET', endpoint, params=params, headers=headers, timeout=timeout)
    
    def post(
        self,
        endpoint: str,
        json_data: Optional[Union[Dict, List]] = None,
        data: Optional[Union[Dict, List, str, bytes]] = None,
        params: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        files: Optional[Dict] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """POST 요청을 실행합니다."""
        return self.request(
            'POST', endpoint,
            json_data=json_data,
            data=data,
            params=params,
            headers=headers,
            files=files,
            timeout=timeout
        )
    
    def put(
        self,
        endpoint: str,
        json_data: Optional[Union[Dict, List]] = None,
        data: Optional[Union[Dict, List, str, bytes]] = None,
        params: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """PUT 요청을 실행합니다."""
        return self.request(
            'PUT', endpoint,
            json_data=json_data,
            data=data,
            params=params,
            headers=headers,
            timeout=timeout
        )
    
    def patch(
        self,
        endpoint: str,
        json_data: Optional[Union[Dict, List]] = None,
        data: Optional[Union[Dict, List, str, bytes]] = None,
        params: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """PATCH 요청을 실행합니다."""
        return self.request(
            'PATCH', endpoint,
            json_data=json_data,
            data=data,
            params=params,
            headers=headers,
            timeout=timeout
        )
    
    def delete(
        self,
        endpoint: str,
        params: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """DELETE 요청을 실행합니다."""
        return self.request('DELETE', endpoint, params=params, headers=headers, timeout=timeout)
    
    def head(
        self,
        endpoint: str,
        params: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None
    ) -> requests.Response:
        """HEAD 요청을 실행합니다."""
        return self._make_request('HEAD', endpoint, params=params, headers=headers, timeout=timeout)
    
    def options(
        self,
        endpoint: str,
        params: Optional[Union[Dict, List]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None
    ) -> requests.Response:
        """OPTIONS 요청을 실행합니다."""
        return self._make_request('OPTIONS', endpoint, params=params, headers=headers, timeout=timeout)

