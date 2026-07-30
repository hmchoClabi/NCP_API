import unittest
from unittest.mock import MagicMock, patch

import main


class MainTests(unittest.TestCase):
    @patch("main.validate_settings")
    @patch("main.setup_logging")
    @patch("main.ReportRunner")
    def test_no_period_arguments_preserves_legacy_target_month(
        self,
        runner_class,
        _setup_logging,
        _validate_settings,
    ):
        runner = runner_class.return_value

        main.main([])

        runner_class.assert_called_once_with(output_dir=None)
        runner.run.assert_called_once_with(
            target_month="2026-06",
            target_day=None,
            start_date=None,
            end_date=None,
        )

    @patch("main.validate_settings")
    @patch("main.setup_logging")
    @patch("main.ReportRunner")
    def test_range_arguments_are_forwarded(
        self,
        runner_class,
        _setup_logging,
        _validate_settings,
    ):
        runner = runner_class.return_value

        main.main(
            [
                "--start-date",
                "2026-07-01",
                "--end-date",
                "2026-07-15",
                "--output-dir",
                "custom-reports",
            ]
        )

        runner_class.assert_called_once_with(output_dir="custom-reports")
        runner.run.assert_called_once_with(
            target_month=None,
            target_day=None,
            start_date="2026-07-01",
            end_date="2026-07-15",
        )

    def test_incomplete_range_is_rejected_before_execution(self):
        with self.assertRaises(SystemExit) as context:
            main.main(["--start-date", "2026-07-01"])

        self.assertEqual(context.exception.code, 2)

    @patch("main.validate_settings")
    @patch("main.setup_logging")
    @patch("main.ReportRunner")
    def test_runtime_value_error_is_not_reported_as_argument_error(
        self,
        runner_class,
        _setup_logging,
        _validate_settings,
    ):
        runner = runner_class.return_value
        runner.run.side_effect = ValueError("invalid API response")

        with self.assertRaisesRegex(ValueError, "invalid API response"):
            main.main([])

    @patch("main.NCP_ACCESS_KEY", "")
    @patch("main.NCP_SECRET_KEY", "")
    def test_validate_settings_reports_missing_credentials(self):
        with self.assertLogs("main", level="ERROR") as logs:
            with self.assertRaises(SystemExit) as context:
                main.validate_settings()

        self.assertEqual(context.exception.code, 1)
        self.assertIn("NCP_ACCESS_KEY, NCP_SECRET_KEY", logs.output[0])

    @patch("main.logging.basicConfig")
    @patch("main.logging.FileHandler", return_value=MagicMock())
    @patch("main.LOG_FILE", "ncp_report.log")
    def test_setup_logging_accepts_filename_without_directory(
        self,
        _file_handler,
        basic_config,
    ):
        main.setup_logging()

        basic_config.assert_called_once()


if __name__ == "__main__":
    unittest.main()
