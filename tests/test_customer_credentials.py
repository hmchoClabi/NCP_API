import os
import unittest
from unittest.mock import MagicMock, patch

from app.apifactory import APIFactory
from app.customer import CustomerProfile, customer_id_from_name
from app.runner import ReportRunner
from utils.credential_provider import (
    EnvironmentCredentialProvider,
    StaticCredentialProvider,
)


class CustomerCredentialTests(unittest.TestCase):
    def test_environment_provider_builds_gov_credentials(self):
        customer = CustomerProfile(
            customer_id="gov-customer",
            customer_name="공공 고객",
            api_type="gov",
            region="KRS",
        )

        with patch.dict(
            os.environ,
            {
                "NCP_ACCESS_KEY": "GOV-ACCESS",
                "NCP_SECRET_KEY": "GOV-SECRET",
            },
            clear=False,
        ):
            credentials = EnvironmentCredentialProvider().get_credentials(
                customer
            )

        self.assertEqual(credentials.access_key, "GOV-ACCESS")
        self.assertEqual(credentials.secret_key, "GOV-SECRET")
        self.assertEqual(credentials.api_type, "gov")
        self.assertEqual(credentials.region, "KRS")
        self.assertEqual(credentials.account_name, "공공 고객")
        self.assertNotIn("GOV-SECRET", repr(credentials))

    def test_static_provider_supports_programmatic_injection(self):
        customer = CustomerProfile(
            customer_id="private-customer",
            customer_name="민간 고객",
            api_type="public",
            region="KR",
        )
        provider = StaticCredentialProvider(
            access_key="PUBLIC-ACCESS",
            secret_key="PUBLIC-SECRET",
        )

        credentials = provider.get_credentials(customer)

        self.assertEqual(credentials.access_key, "PUBLIC-ACCESS")
        self.assertEqual(credentials.api_type, "public")
        self.assertEqual(credentials.account_name, "민간 고객")

    def test_api_factory_injects_same_credentials_into_api_instances(self):
        customer = CustomerProfile(
            customer_id="customer-one",
            customer_name="Customer One",
            api_type="gov",
            region="KR",
        )
        credentials = StaticCredentialProvider(
            access_key="ACCESS",
            secret_key="SECRET",
        ).get_credentials(customer)
        api_class = MagicMock()
        api_instance = api_class.return_value
        factory = APIFactory(credentials=credentials)
        factory._registry = {"test": api_class}

        result = factory.get("test")

        self.assertIs(result, api_instance)
        api_class.assert_called_once_with(credentials=credentials)

    def test_runner_isolates_non_default_customer_output(self):
        customer = CustomerProfile(
            customer_id="customer-001",
            customer_name="Customer One",
        )

        runner = ReportRunner(
            output_dir="reports",
            api_factory=MagicMock(),
            customer=customer,
        )

        self.assertEqual(
            runner.output_dir.replace("\\", "/"),
            "reports/customer-001",
        )

    def test_customer_id_can_be_derived_from_korean_name(self):
        customer_id = customer_id_from_name("테스트 고객")

        self.assertRegex(customer_id, r"^customer-[a-f0-9]{8}$")
        self.assertEqual(customer_id, customer_id_from_name("테스트 고객"))

    def test_public_and_gov_regions_are_validated(self):
        CustomerProfile(
            customer_id="public-customer",
            customer_name="Public",
            api_type="public",
            region="JPN",
        )
        CustomerProfile(
            customer_id="gov-customer",
            customer_name="Government",
            api_type="gov",
            region="KRS",
        )

        with self.assertRaises(ValueError):
            CustomerProfile(
                customer_id="invalid",
                customer_name="Invalid",
                api_type="public",
                region="KRS",
            )


if __name__ == "__main__":
    unittest.main()
