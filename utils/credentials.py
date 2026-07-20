from dataclasses import dataclass


@dataclass(frozen=True)
class NCPCredentials:
    access_key: str
    secret_key: str
    api_type: str = "public"
    region: str = "KR"
    account_name: str | None = None