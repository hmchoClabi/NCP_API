"""네이버 클라우드 플랫폼 API 실행 진입점."""

import argparse
import logging
import os
import sys
from typing import Optional

from config.settings import LOG_FILE, LOG_LEVEL
from ncp_api import CertificateMgrAPI
from utils.client_factory import NCPClientFactory
from utils.credentials import CredentialProvider, EnvCredentialProvider


def setup_logging() -> None:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ],
    )


def validate_credentials(provider: CredentialProvider) -> None:
    credentials = provider.get_credentials()
    if not credentials.access_key or not credentials.secret_key:
        raise RuntimeError('NCP_ACCESS_KEY 또는 NCP_SECRET_KEY가 설정되지 않았습니다.')


def run_certificate_list(factory: NCPClientFactory, tenant_id: str | None = None) -> dict:
    client = factory.create('certificatemanager', tenant_id=tenant_id)
    api = CertificateMgrAPI(client)
    return api.get_certificate_list()


def main(command: Optional[str] = None, tenant_id: str | None = None) -> int:
    setup_logging()
    logger = logging.getLogger(__name__)
    provider = EnvCredentialProvider()
    factory = NCPClientFactory(credential_provider=provider)

    try:
        validate_credentials(provider)
    except RuntimeError as exc:
        logger.error(str(exc))
        return 1

    action = command or 'certificate-list'

    if action == 'certificate-list':
        response = run_certificate_list(factory=factory, tenant_id=tenant_id)
        print(response)
        return 0

    logger.error('지원하지 않는 커맨드입니다: %s', action)
    return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='NCP API 실행 도구')
    parser.add_argument(
        '--command',
        choices=['certificate-list'],
        default='certificate-list',
        help='실행할 명령',
    )
    parser.add_argument(
        '--tenant-id',
        default=None,
        help='멀티 테넌트 인증 provider 사용 시 조회할 tenant 식별자',
    )
    args = parser.parse_args()
    raise SystemExit(main(args.command, args.tenant_id))
