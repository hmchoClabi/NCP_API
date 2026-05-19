"""NCP API Client Factory."""

from __future__ import annotations

from config.settings import API_ENDPOINTS
from utils.common_rest import NCPBaseClient
from utils.credentials import CredentialProvider, EnvCredentialProvider


class NCPClientFactory:
    """서비스 이름으로 NCPBaseClient를 생성합니다."""

    def __init__(self, credential_provider: CredentialProvider | None = None):
        self.credential_provider = credential_provider or EnvCredentialProvider()

    def create(self, service: str, tenant_id: str | None = None) -> NCPBaseClient:
        try:
            base_url = API_ENDPOINTS[service]
        except KeyError as exc:
            available = ", ".join(sorted(API_ENDPOINTS.keys()))
            raise ValueError(f"지원하지 않는 서비스입니다: {service}. 사용 가능: {available}") from exc

        credentials = self.credential_provider.get_credentials(service=service, tenant_id=tenant_id)

        if not credentials.access_key or not credentials.secret_key:
            raise RuntimeError(
                f"서비스({service}) 인증키가 비어 있습니다. credential provider 설정을 확인하세요."
            )

        return NCPBaseClient(
            access_key=credentials.access_key,
            secret_key=credentials.secret_key,
            base_url=base_url,
        )
