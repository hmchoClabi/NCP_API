import importlib
import os
import unittest
from unittest.mock import patch

import config.settings as settings
from config.endpoints import (
    build_api_endpoints,
    get_kubernetes_endpoint,
)


class EndpointTests(unittest.TestCase):
    def test_normalizes_supported_api_type_and_region(self):
        endpoints = build_api_endpoints(" PUBLIC ", " jpn ")

        self.assertIn("/vnks/jpn-v2", endpoints["kubernetes"])
        for endpoint_key in ("cdn", "nas_classic", "containerregistry"):
            with self.subTest(endpoint_key=endpoint_key):
                self.assertNotIn(endpoint_key, endpoints)

    def test_rejects_unknown_or_incompatible_region(self):
        for api_type, region in (
            ("public", "KRS"),
            ("gov", "JPN"),
            ("public", "UNKNOWN"),
            ("invalid", "KR"),
        ):
            with self.subTest(api_type=api_type, region=region):
                with self.assertRaises(ValueError):
                    build_api_endpoints(api_type, region)

        with self.assertRaises(ValueError):
            get_kubernetes_endpoint("gov", "SGN")


class SettingsTests(unittest.TestCase):
    def tearDown(self):
        # reload 테스트가 다른 테스트의 모듈 전역값에 영향을 남기지 않게 복구합니다.
        importlib.reload(settings)

    def test_process_environment_wins_over_dotenv(self):
        overrides = {
            "NCP_ACCESS_KEY": "PROCESS-ACCESS",
            "NCP_SECRET_KEY": "PROCESS-SECRET",
            "NCP_API_TYPE": "PUBLIC",
            "NCP_REGION": "jpn",
            "API_TIMEOUT": "17",
            "API_RETRY_COUNT": "2",
        }
        with patch.dict(os.environ, overrides, clear=False):
            reloaded = importlib.reload(settings)

            self.assertEqual(reloaded.NCP_ACCESS_KEY, "PROCESS-ACCESS")
            self.assertEqual(reloaded.NCP_SECRET_KEY, "PROCESS-SECRET")
            self.assertEqual(reloaded.NCP_API_TYPE, "public")
            self.assertEqual(reloaded.NCP_REGION, "JPN")
            self.assertEqual(reloaded.API_TIMEOUT, 17)
            self.assertEqual(reloaded.API_RETRY_COUNT, 2)

    def test_positive_integer_settings_validation(self):
        for name in ("API_TIMEOUT", "API_RETRY_COUNT"):
            for invalid in ("0", "-1", "not-a-number"):
                with self.subTest(name=name, invalid=invalid):
                    with patch.dict(os.environ, {name: invalid}, clear=False):
                        with self.assertRaisesRegex(ValueError, name):
                            settings._read_positive_int(name, 1)

    def test_invalid_region_fails_during_settings_load(self):
        with patch.dict(
            os.environ,
            {
                "NCP_API_TYPE": "public",
                "NCP_REGION": "UNKNOWN",
                "API_TIMEOUT": "30",
                "API_RETRY_COUNT": "3",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "region"):
                importlib.reload(settings)


if __name__ == "__main__":
    unittest.main()
