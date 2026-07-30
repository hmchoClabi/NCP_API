from dataclasses import dataclass, field


@dataclass(frozen=True)
class NCPCredentials:
    access_key: str
    secret_key: str = field(repr=False)
    api_type: str = "public"
    region: str = "KR"
    account_name: str | None = None
