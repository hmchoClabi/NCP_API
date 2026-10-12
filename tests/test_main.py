import unittest
from unittest.mock import MagicMock, patch

import main


class MainTests(unittest.TestCase):
    @patch("main.validate_settings")
    @patch("main.setup_logging")
    @patch("main.ReportRunner")
    def test_no_period_arguments_use_runner_default_period(
        self,
        runner_class,
        _setup_logging,
        _validate_settings,
    ):
        runner = runner_class.return_value

        main.main([])

        runner_class.assert_called_once()
        runner_arguments = runner_class.call_args.kwargs
        self.assertIsNone(runner_arguments["output_dir"])
        self.assertEqual(
            runner_arguments["customer"].customer_id,
            "default",
        )
        self.assertIsNotNone(runner_arguments["api_factory"])
        runner.run.assert_called_once_with(
            target_month=None,
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

        runner_class.assert_called_once()
        runner_arguments = runner_class.call_args.kwargs
        self.assertEqual(
            runner_arguments["output_dir"],
            "custom-reports",
        )
        self.assertEqual(
            runner_arguments["customer"].customer_id,
            "default",
        )
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
    def test_datetime_range_is_forwarded(
        self,
        runner_class,
        _setup_logging,
        _validate_settings,
    ):
        runner = runner_class.return_value

        main.main(
            [
                "--start-datetime",
                "2026-08-02 14:00",
                "--end-datetime",
                "2026-08-02 15:00",
            ]
        )

        expected = {
            "target_month": None,
            "target_day": None,
            "start_date": None,
            "end_date": None,
            "start_datetime": "2026-08-02 14:00",
            "end_datetime": "2026-08-02 15:00",
        }
        runner.get_period.assert_called_once_with(**expected)
        runner.run.assert_called_once_with(**expected)

    def test_incomplete_datetime_range_is_rejected_before_execution(self):
        with self.assertRaises(SystemExit) as context:
            main.main(["--start-datetime", "2026-08-02 14:00"])

        self.assertEqual(context.exception.code, 2)

    @patch("main.validate_settings")
    @patch("main.setup_logging")
    @patch("main.ReportRunner")
    def test_weekly_target_is_forwarded(
        self,
        runner_class,
        _setup_logging,
        _validate_settings,
    ):
        runner = runner_class.return_value

        main.main(["--target-week", "2026-w31"])

        expected = {
            "target_month": None,
            "target_day": None,
            "start_date": None,
            "end_date": None,
            "target_week": "2026-W31",
        }
        runner.get_period.assert_called_once_with(**expected)
        runner.run.assert_called_once_with(**expected)

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

    @patch("main.send_report_email")
    @patch("main.validate_settings")
    @patch("main.setup_logging")
    @patch("main.ReportRunner")
    def test_send_email_flag_delivers_generated_report(
        self,
        runner_class,
        _setup_logging,
        _validate_settings,
        send_report_email,
    ):
        runner = runner_class.return_value
        report = runner.run.return_value

        main.main(
            [
                "--target-day",
                "2026-07-29",
                "--send-email",
                "--email-to",
                "first@example.com,second@example.com",
            ]
        )

        send_report_email.assert_called_once_with(
            report=report,
            runner=runner,
            recipient_values=["first@example.com,second@example.com"],
        )

    @patch("main.HtmlReportRenderer")
    @patch("main.SMTPMailer")
    @patch("main.SMTPConfig.from_env")
    def test_send_report_email_includes_html_summary(
        self,
        config_from_env,
        mailer_class,
        renderer_class,
    ):
        report = MagicMock()
        report.period = {
            "period_type": "day",
            "is_full_month": False,
            "start_dt": "2026-08-18 00:00:00",
            "end_dt": "2026-08-18 23:59:59",
            "file_suffix": "20260818_20260818",
        }
        report.customer = {"name": "테스트 고객"}
        report.generated_at = "2026-08-19 01:00:00"
        runner = MagicMock(output_dir="output/report/test")
        renderer_class.return_value.render_email_summary.return_value = "<html>summary</html>"
        mailer_class.return_value.send.return_value = "message-id"

        result = main.send_report_email(
            report,
            runner,
            ["viewer@example.com"],
        )

        self.assertEqual(result, "message-id")
        config_from_env.assert_called_once_with()
        renderer_class.return_value.render_email_summary.assert_called_once_with(report)
        self.assertEqual(
            mailer_class.return_value.send.call_args.kwargs["html_body"],
            "<html>summary</html>",
        )

    @patch("main.HtmlReportRenderer")
    @patch("main.SMTPMailer")
    @patch("main.SMTPConfig.from_env")
    def test_send_report_email_labels_weekly_period(
        self,
        _config_from_env,
        mailer_class,
        _renderer_class,
    ):
        report = MagicMock()
        report.period = {
            "period_type": "week",
            "is_full_month": False,
            "start_dt": "2026-07-27 00:00:00",
            "end_dt": "2026-08-02 23:59:59",
            "file_suffix": "20260727_20260802",
        }
        report.customer = {"name": "테스트 고객"}
        report.generated_at = "2026-08-03 09:00:00"
        runner = MagicMock(output_dir="output/report/test")

        main.send_report_email(report, runner, ["viewer@example.com"])

        send = mailer_class.return_value.send.call_args.kwargs
        self.assertIn("NCP 주간 보고서", send["subject"])
        self.assertIn("보고서 유형: 주간", send["body"])

    def test_customer_and_gov_options_are_injected_per_run(self):
        with (
            patch.dict(
                "main.os.environ",
                {
                    "NCP_ACCESS_KEY": "GOV-ACCESS",
                    "NCP_SECRET_KEY": "GOV-SECRET",
                },
                clear=False,
            ),
            patch("main.setup_logging"),
            patch("main.validate_settings") as validate_settings,
            patch("main.APIFactory") as api_factory_class,
            patch("main.ReportRunner") as runner_class,
        ):
            main.main(
                [
                    "--target-day",
                    "2026-07-29",
                    "--customer-id",
                    "gov-customer-001",
                    "--customer-name",
                    "공공 고객",
                    "--api-type",
                    "gov",
                    "--region",
                    "KRS",
                ]
            )

        credentials = api_factory_class.call_args.kwargs["credentials"]
        self.assertEqual(credentials.access_key, "GOV-ACCESS")
        self.assertEqual(credentials.secret_key, "GOV-SECRET")
        self.assertEqual(credentials.api_type, "gov")
        self.assertEqual(credentials.region, "KRS")
        validate_settings.assert_called_once_with(credentials)

        runner_arguments = runner_class.call_args.kwargs
        customer = runner_arguments["customer"]
        self.assertEqual(customer.customer_id, "gov-customer-001")
        self.assertEqual(customer.customer_name, "공공 고객")
        self.assertEqual(customer.api_type, "gov")
        self.assertIs(
            runner_arguments["api_factory"],
            api_factory_class.return_value,
        )

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
