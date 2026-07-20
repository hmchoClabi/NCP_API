from config.settings import (
    NCP_ACCESS_KEY,
    NCP_SECRET_KEY,
    NCP_API_TYPE,
    NCP_REGION,
)
from utils.credentials import NCPCredentials


def get_default_credentials() -> NCPCredentials:
    return NCPCredentials(
        access_key=NCP_ACCESS_KEY,
        secret_key=NCP_SECRET_KEY,
        api_type=NCP_API_TYPE,
        region=NCP_REGION,
        account_name="default",
    )