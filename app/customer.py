import re
from hashlib import sha256
from dataclasses import dataclass
from typing import Any, Dict

from config.endpoints import build_api_endpoints


CUSTOMER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def customer_id_from_name(customer_name: str) -> str:
    normalized = customer_name.strip().lower()
    slug = re.sub(r"[^a-z0-9._-]+", "-", normalized).strip(".-_")
    digest = sha256(normalized.encode("utf-8")).hexdigest()[:8]
    return f"{(slug or 'customer')[:54]}-{digest}"


@dataclass(frozen=True)
class CustomerProfile:
    customer_id: str
    customer_name: str
    api_type: str = "public"
    region: str = "KR"
    credential_ref: str | None = None
    cloud_account_id: str | None = None
    cloud_account_code: str | None = None

    def __post_init__(self) -> None:
        customer_id = self.customer_id.strip()
        customer_name = self.customer_name.strip()
        api_type = self.api_type.strip().lower()
        region = self.region.strip().upper()

        if not CUSTOMER_ID_PATTERN.fullmatch(customer_id):
            raise ValueError(
                "customer_id must start with an alphanumeric character and "
                "contain only letters, numbers, '.', '_', or '-' "
                "(maximum 64 characters)."
            )
        if not customer_name:
            raise ValueError("customer_name is required.")

        # Reuse the existing endpoint validation so public/GOV behavior cannot
        # drift between customer configuration and API construction.
        build_api_endpoints(api_type=api_type, region=region)

        object.__setattr__(self, "customer_id", customer_id)
        object.__setattr__(self, "customer_name", customer_name)
        object.__setattr__(self, "api_type", api_type)
        object.__setattr__(self, "region", region)

    @property
    def is_default(self) -> bool:
        return self.customer_id == "default"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.customer_id,
            "name": self.customer_name,
            "api_type": self.api_type,
            "region": self.region,
            "credential_ref": self.credential_ref,
            "cloud_account_id": self.cloud_account_id,
            "cloud_account_code": self.cloud_account_code,
        }
