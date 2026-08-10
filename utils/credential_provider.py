import os
from dataclasses import dataclass, field
from typing import Protocol

from app.customer import CustomerProfile
from config.settings import (
    NCP_ACCESS_KEY,
    NCP_SECRET_KEY,
    NCP_API_TYPE,
    NCP_REGION,
)
from utils.credentials import NCPCredentials


class CredentialProvider(Protocol):
    """고객별 NCP 자격증명을 제공하는 객체의 공개 호환 계약."""

    def get_credentials(
        self,
        customer: CustomerProfile,
    ) -> NCPCredentials:
        ...


@dataclass(frozen=True)
class EnvironmentCredentialProvider:
    access_key_variable: str = "NCP_ACCESS_KEY"
    secret_key_variable: str = "NCP_SECRET_KEY"

    def get_credentials(
        self,
        customer: CustomerProfile,
    ) -> NCPCredentials:
        return NCPCredentials(
            access_key=os.getenv(self.access_key_variable, ""),
            secret_key=os.getenv(self.secret_key_variable, ""),
            api_type=customer.api_type,
            region=customer.region,
            account_name=customer.customer_name,
        )


@dataclass(frozen=True)
class StaticCredentialProvider:
    access_key: str
    secret_key: str = field(repr=False)

    def get_credentials(
        self,
        customer: CustomerProfile,
    ) -> NCPCredentials:
        return NCPCredentials(
            access_key=self.access_key,
            secret_key=self.secret_key,
            api_type=customer.api_type,
            region=customer.region,
            account_name=customer.customer_name,
        )


def get_default_credentials() -> NCPCredentials:
    return NCPCredentials(
        access_key=NCP_ACCESS_KEY,
        secret_key=NCP_SECRET_KEY,
        api_type=NCP_API_TYPE,
        region=NCP_REGION,
        account_name="default",
    )
