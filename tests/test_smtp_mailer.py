import os
import smtplib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.mailers import (
    SMTPAuthenticationFailedError,
    SMTPConfig,
    SMTPMailer,
    SMTPSenderRejectedError,
    parse_recipients,
)


class SMTPMailerTests(unittest.TestCase):
    def test_parse_recipients_splits_deduplicates_and_validates(self):
        recipients = parse_recipients(
            [
                "first@example.com, second@example.com",
                "FIRST@example.com",
            ]
        )

        self.assertEqual(
            recipients,
            ["first@example.com", "second@example.com"],
        )
        with self.assertRaisesRegex(ValueError, "Invalid email recipient"):
            parse_recipients(["not-an-address"])

    def test_config_is_loaded_from_environment(self):
        environment = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "2525",
            "SMTP_FROM": "reports@example.com",
            "SMTP_USERNAME": "report-user",
            "SMTP_PASSWORD": "secret",
            "SMTP_USE_TLS": "true",
            "SMTP_USE_SSL": "false",
            "SMTP_TIMEOUT": "15",
        }

        with patch.dict(os.environ, environment, clear=False):
            config = SMTPConfig.from_env()

        self.assertEqual(config.host, "smtp.example.com")
        self.assertEqual(config.port, 2525)
        self.assertEqual(config.sender, "reports@example.com")
        self.assertEqual(config.username, "report-user")
        self.assertEqual(config.password, "secret")
        self.assertTrue(config.use_tls)
        self.assertFalse(config.use_ssl)
        self.assertEqual(config.timeout, 15)
        self.assertNotIn("secret", repr(config))

    @patch("app.mailers.smtp_mailer.ssl.create_default_context")
    @patch("app.mailers.smtp_mailer.smtplib.SMTP")
    def test_send_uses_starttls_login_and_html_attachment(
        self,
        smtp_class,
        create_context,
    ):
        client = MagicMock()
        smtp_class.return_value.__enter__.return_value = client
        context = create_context.return_value
        config = SMTPConfig(
            host="smtp.example.com",
            port=587,
            sender="reports@example.com",
            username="report-user",
            password="secret",
            use_tls=True,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            attachment = Path(temp_dir) / "report.html"
            attachment.write_text("<html>report</html>", encoding="utf-8")

            message_id = SMTPMailer(config).send(
                subject="NCP report",
                body="The report is attached.",
                recipients=[
                    "first@example.com",
                    "second@example.com",
                ],
                attachments=[attachment],
            )

        smtp_class.assert_called_once_with(
            "smtp.example.com",
            587,
            timeout=30,
        )
        client.starttls.assert_called_once_with(context=context)
        client.login.assert_called_once_with("report-user", "secret")
        client.send_message.assert_called_once()

        message = client.send_message.call_args.args[0]
        self.assertEqual(message["Subject"], "NCP report")
        self.assertEqual(
            client.send_message.call_args.kwargs["to_addrs"],
            ["first@example.com", "second@example.com"],
        )
        self.assertEqual(
            message.get_body(preferencelist=("plain",)).get_content().strip(),
            "The report is attached.",
        )
        attachments = list(message.iter_attachments())
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].get_filename(), "report.html")
        self.assertTrue(message_id.startswith("<"))

    def test_send_rejects_missing_attachment_before_connecting(self):
        mailer = SMTPMailer(
            SMTPConfig(
                host="smtp.example.com",
                port=587,
                sender="reports@example.com",
            )
        )

        with self.assertRaises(FileNotFoundError):
            mailer.send(
                subject="NCP report",
                body="Body",
                recipients=["recipient@example.com"],
                attachments=["missing-report.html"],
            )

    @patch("app.mailers.smtp_mailer.ssl.create_default_context")
    @patch("app.mailers.smtp_mailer.smtplib.SMTP_SSL")
    def test_naver_authentication_error_has_actionable_message(
        self,
        smtp_ssl_class,
        _create_context,
    ):
        client = MagicMock()
        smtp_ssl_class.return_value.__enter__.return_value = client
        client.login.side_effect = smtplib.SMTPAuthenticationError(
            535,
            b"Username and Password not accepted",
        )
        mailer = SMTPMailer(
            SMTPConfig(
                host="smtp.naver.com",
                port=465,
                sender="reporter@naver.com",
                username="reporter",
                password="application-password",
                use_tls=False,
                use_ssl=True,
            )
        )

        with self.assertRaisesRegex(
            SMTPAuthenticationFailedError,
            "application password",
        ):
            mailer.send(
                subject="NCP report",
                body="Body",
                recipients=["recipient@example.com"],
            )

    @patch("app.mailers.smtp_mailer.ssl.create_default_context")
    @patch("app.mailers.smtp_mailer.smtplib.SMTP_SSL")
    def test_naver_works_authentication_error_has_actionable_message(
        self,
        smtp_ssl_class,
        _create_context,
    ):
        client = MagicMock()
        smtp_ssl_class.return_value.__enter__.return_value = client
        client.login.side_effect = smtplib.SMTPAuthenticationError(
            535,
            b"Username and Password not accepted",
        )
        mailer = SMTPMailer(
            SMTPConfig(
                host="smtp.worksmobile.com",
                port=465,
                sender="reporter@example.com",
                username="reporter@example.com",
                password="third-party-app-password",
                use_tls=False,
                use_ssl=True,
            )
        )

        with self.assertRaisesRegex(
            SMTPAuthenticationFailedError,
            "full WORKS email address",
        ):
            mailer.send(
                subject="NCP report",
                body="Body",
                recipients=["recipient@example.com"],
            )

    @patch("app.mailers.smtp_mailer.ssl.create_default_context")
    @patch("app.mailers.smtp_mailer.smtplib.SMTP_SSL")
    def test_naver_works_sender_rejection_has_actionable_message(
        self,
        smtp_ssl_class,
        _create_context,
    ):
        client = MagicMock()
        smtp_ssl_class.return_value.__enter__.return_value = client
        client.send_message.side_effect = smtplib.SMTPSenderRefused(
            554,
            b"The sender address is unauthorized",
            "reports@example.com",
        )
        mailer = SMTPMailer(
            SMTPConfig(
                host="smtp.worksmobile.com",
                port=465,
                sender="reports@example.com",
                username="reporter@company.example",
                password="third-party-app-password",
                use_tls=False,
                use_ssl=True,
            )
        )

        with self.assertRaisesRegex(
            SMTPSenderRejectedError,
            "set SMTP_FROM",
        ):
            mailer.send(
                subject="NCP report",
                body="Body",
                recipients=["recipient@example.com"],
            )


if __name__ == "__main__":
    unittest.main()
