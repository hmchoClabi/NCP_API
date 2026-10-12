import unittest
from unittest.mock import patch

from webapp.cli import prompt_new_password


class WebCliTests(unittest.TestCase):
    def test_password_prompt_retries_short_and_mismatched_values(self):
        with (
            patch.dict("webapp.cli.os.environ", {}, clear=True),
            patch(
                "webapp.cli.getpass.getpass",
                side_effect=[
                    "short",
                    "long-password-one",
                    "different-password",
                    "long-password-two",
                    "long-password-two",
                ],
            ),
        ):
            password = prompt_new_password("TEST_PASSWORD", "Test")

        self.assertEqual(password, "long-password-two")

    def test_environment_password_is_validated(self):
        with patch.dict("webapp.cli.os.environ", {"TEST_PASSWORD": "short"}, clear=True):
            with self.assertRaisesRegex(ValueError, "at least 12"):
                prompt_new_password("TEST_PASSWORD", "Test")


if __name__ == "__main__":
    unittest.main()
