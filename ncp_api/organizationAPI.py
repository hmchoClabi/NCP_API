from typing import Any

from ncp_api.base import BaseNCPAPI


class OrganizationAPI(BaseNCPAPI):
    """Read-only NAVER Cloud Organization discovery API."""

    ENDPOINT_KEY = "organization"

    def get_organization(self) -> dict[str, Any]:
        return self.client.get("/open-api/v1/org")

    def get_account_group_tree(self) -> list[dict[str, Any]]:
        response = self.client.get("/open-api/v1/policy/tree")
        return response if isinstance(response, list) else []
