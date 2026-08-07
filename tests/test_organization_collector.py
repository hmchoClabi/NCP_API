import unittest

import requests

from collectors.organizationcollector import OrganizationCollector


class FakeFactory:
    def __init__(self, api):
        self.api = api

    def get(self, name):
        if name != "organization":
            raise KeyError(name)
        return self.api


class MasterAPI:
    def get_organization(self):
        return {
            "organizationNo": 10,
            "organizationName": "Example Org",
            "masterMemberNo": 100,
            "masterMemberYn": "Y",
        }

    def get_account_group_tree(self):
        return [
            {"groupYn": "Y", "organizationGroupNo": 1},
            {
                "memberNo": 100, "memberAlias": "Master",
                "memberStatusCode": "JOIN", "masterMemberYn": "Y",
            },
            {
                "memberNo": 200, "memberAlias": "Child",
                "memberStatusCode": "JOIN", "masterMemberYn": "N",
            },
            {
                "memberNo": 300, "memberAlias": "Pending",
                "memberStatusCode": "INVT", "masterMemberYn": "N",
            },
        ]


class DeniedAPI:
    def get_organization(self):
        response = requests.Response()
        response.status_code = 403
        raise requests.HTTPError("forbidden", response=response)


class OrganizationCollectorTests(unittest.TestCase):
    def test_master_discovers_joined_accounts(self):
        result = OrganizationCollector(FakeFactory(MasterAPI())).discover()

        self.assertEqual(result["scope"], "ORGANIZATION")
        self.assertEqual(
            [member["member_no"] for member in result["members"]],
            ["100", "200"],
        )

    def test_permission_denied_safely_falls_back_to_self(self):
        result = OrganizationCollector(FakeFactory(DeniedAPI())).discover()

        self.assertEqual(result["scope"], "SELF")
        self.assertEqual(result["reason"], "NOT_MASTER_OR_PERMISSION_DENIED")


if __name__ == "__main__":
    unittest.main()
