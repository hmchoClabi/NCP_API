from __future__ import annotations

from typing import Any

import requests

from utils.common_rest import safe_exception_message


class OrganizationCollector:
    """Discover an Organization without turning authorization gaps into failures."""

    def __init__(self, api_factory: Any):
        self.api_factory = api_factory

    def discover(self) -> dict[str, Any]:
        try:
            api = self.api_factory.get("organization")
            organization = api.get_organization()
        except (AttributeError, KeyError, ValueError) as exc:
            return self._self_only("UNSUPPORTED_ENVIRONMENT", exc)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in {401, 403, 404}:
                return self._self_only("NOT_MASTER_OR_PERMISSION_DENIED", exc)
            return self._self_only("DISCOVERY_FAILED", exc)
        except requests.RequestException as exc:
            return self._self_only("DISCOVERY_FAILED", exc)

        if not isinstance(organization, dict) or organization.get("masterMemberYn") != "Y":
            return self._self_only("NOT_MASTER")

        try:
            tree = api.get_account_group_tree()
        except requests.RequestException as exc:
            return self._self_only("ACCOUNT_LIST_FAILED", exc)

        members: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in tree:
            if not isinstance(row, dict) or row.get("groupYn") == "Y":
                continue
            member_no = str(row.get("memberNo") or "").strip()
            if not member_no or member_no in seen:
                continue
            status = str(row.get("memberStatusCode") or "").strip().upper()
            if status and status != "JOIN":
                continue
            seen.add(member_no)
            members.append({
                "member_no": member_no,
                "display_name": str(
                    row.get("memberAlias") or row.get("displayName")
                    or member_no
                )[:200],
                "group_no": str(row.get("organizationGroupNo") or "")[:30],
                "group_path": str(row.get("wholePath") or "")[:500],
                "is_master": row.get("masterMemberYn") == "Y",
                "status": status or "JOIN",
            })

        master_no = str(organization.get("masterMemberNo") or "").strip()
        if master_no and master_no not in seen:
            members.insert(0, {
                "member_no": master_no,
                "display_name": str(
                    organization.get("organizationName") or "Master"
                )[:200],
                "group_no": "",
                "group_path": "",
                "is_master": True,
                "status": "JOIN",
            })
        return {
            "scope": "ORGANIZATION",
            "reason": "MASTER_CONFIRMED",
            "organization_no": str(organization.get("organizationNo") or "")[:30],
            "organization_name": str(organization.get("organizationName") or "")[:200],
            "master_member_no": master_no,
            "members": members,
        }

    @staticmethod
    def _self_only(reason: str, exc: BaseException | None = None) -> dict[str, Any]:
        result = {"scope": "SELF", "reason": reason, "members": []}
        if exc is not None:
            result["message"] = safe_exception_message(exc)[:500]
        return result
