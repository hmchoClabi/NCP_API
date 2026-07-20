import logging

from config.endpoints import build_api_endpoints
from utils.common_rest import NCPBaseClient
from utils.credentials import NCPCredentials
from utils.credential_provider import get_default_credentials

logger = logging.getLogger(__name__)


class BaseNCPAPI:
    
    ENDPOINT_KEY: str = ""

    def __init__(
        self,
        credentials: NCPCredentials | None = None,
        client: NCPBaseClient | None = None,
    ):
        self.credentials: NCPCredentials | None = credentials
        self.client: NCPBaseClient

        if client is not None:
            self.client = client
            logger.debug(
                "%s initialized with custom client",
                self.__class__.__name__,
            )
            return

        self.credentials = credentials or get_default_credentials()

        base_url = self._resolve_base_url(self.credentials)

        self.client = NCPBaseClient(
            access_key=self.credentials.access_key,
            secret_key=self.credentials.secret_key,
            base_url=base_url,
        )

        logger.debug(
            "%s initialized. api_type=%s, region=%s, endpoint_key=%s, base_url=%s",
            self.__class__.__name__,
            self.credentials.api_type,
            self.credentials.region,
            self.ENDPOINT_KEY,
            base_url,
        )

    def _resolve_base_url(self, credentials: NCPCredentials) -> str:
        if not self.ENDPOINT_KEY:
            raise ValueError(
                f"{self.__class__.__name__} ENDPOINT_KEY가 설정되지 않았습니다."
            )

        endpoints = build_api_endpoints(
            api_type=credentials.api_type,
            region=credentials.region,
        )

        base_url = endpoints.get(self.ENDPOINT_KEY)

        if not base_url:
            available_keys = ", ".join(sorted(endpoints.keys()))

            raise ValueError(
                "endpoint 설정을 찾을 수 없습니다. "
                f"api_class={self.__class__.__name__}, "
                f"api_type={credentials.api_type}, "
                f"region={credentials.region}, "
                f"endpoint_key={self.ENDPOINT_KEY}, "
                f"available_keys=[{available_keys}]"
            )

        return base_url

# class BaseNCPAPI:
#     ENDPOINT_KEY: str = ""

#     def __init__(
#         self,
#         credentials: NCPCredentials | None = None,
#         client: NCPBaseClient | None = None,
#     ):

#         print("=" * 60)
#         print(f"API CLASS           : {self.__class__.__name__}")
#         print(f"ENDPOINT_KEY        : {self.ENDPOINT_KEY}")

#         if client is not None:
#             print("CUSTOM CLIENT MODE")
#             self.client = client
#             return

#         if not self.ENDPOINT_KEY:
#             raise ValueError(
#                 f"{self.__class__.__name__} ENDPOINT_KEY가 없습니다."
#             )

#         credentials = credentials or get_default_credentials()

#         self.credentials = credentials

#         print(f"API TYPE            : {credentials.api_type}")
#         print(f"REGION              : {credentials.region}")

#         endpoints = build_api_endpoints(
#             api_type=credentials.api_type,
#             region=credentials.region,
#         )

#         print("-" * 60)
#         # print("AVAILABLE ENDPOINTS")

#         # for key, value in endpoints.items():
#         #     print(f"{key:<25} -> {value}")

#         # print("-" * 60)

#         try:
#             base_url = endpoints[self.ENDPOINT_KEY]

#         except KeyError as e:

#             print("=" * 60)
#             print("ENDPOINT LOOKUP FAILED")
#             print(f"REQUESTED KEY : {self.ENDPOINT_KEY}")
#             print(f"AVAILABLE     : {list(endpoints.keys())}")
#             print("=" * 60)

#             raise ValueError(
#                 f"endpoint 설정을 찾을 수 없습니다. "
#                 f"api_type={credentials.api_type}, "
#                 f"region={credentials.region}, "
#                 f"endpoint_key={self.ENDPOINT_KEY}"
#             ) from e

#         print(f"SELECTED BASE URL   : {base_url}")
#         print("=" * 60)

#         self.client = NCPBaseClient(
#             access_key=credentials.access_key,
#             secret_key=credentials.secret_key,
#             base_url=base_url,
#         )