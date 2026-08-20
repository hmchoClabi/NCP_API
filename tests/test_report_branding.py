import base64
import unittest

from app.customer import CustomerProfile
from app.renderers import HtmlReportRenderer
from app.report_branding import (
    MAX_CUSTOMER_LOGO_BYTES,
    normalize_customer_logo_data_uri,
    validate_customer_logo,
)
from app.report_models import ReportResult


def _png_header(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
        + b"\x00\x00\x00\x00"
    )


class CustomerLogoValidationTests(unittest.TestCase):
    def test_png_is_detected_from_bytes_and_round_trips_as_data_uri(self):
        logo = validate_customer_logo(_png_header(320, 120), "image/png")

        self.assertEqual(logo.content_type, "image/png")
        self.assertEqual((logo.width, logo.height), (320, 120))
        self.assertEqual(
            normalize_customer_logo_data_uri(logo.data_uri),
            logo.data_uri,
        )

    def test_jpeg_and_webp_dimensions_are_read_without_filename_trust(self):
        jpeg = (
            b"\xff\xd8\xff\xc0\x00\x0b\x08"
            + (80).to_bytes(2, "big")
            + (240).to_bytes(2, "big")
            + b"\x01\x01\x11\x00\xff\xd9"
        )
        webp = (
            b"RIFF"
            + (22).to_bytes(4, "little")
            + b"WEBPVP8X"
            + (10).to_bytes(4, "little")
            + b"\x00\x00\x00\x00"
            + (199).to_bytes(3, "little")
            + (99).to_bytes(3, "little")
        )

        jpeg_logo = validate_customer_logo(jpeg, "image/jpeg")
        webp_logo = validate_customer_logo(webp, "image/webp")

        self.assertEqual((jpeg_logo.width, jpeg_logo.height), (240, 80))
        self.assertEqual((webp_logo.width, webp_logo.height), (200, 100))

    def test_svg_oversize_and_content_type_mismatch_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "PNG, JPEG 또는 WebP"):
            validate_customer_logo(b"<svg><script>x</script></svg>", "image/svg+xml")
        with self.assertRaisesRegex(ValueError, "512KB"):
            validate_customer_logo(b"x" * (MAX_CUSTOMER_LOGO_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "일치하지"):
            validate_customer_logo(_png_header(10, 10), "image/jpeg")

    def test_excessive_decoded_dimensions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "800만 픽셀"):
            validate_customer_logo(_png_header(4096, 4096), "image/png")

    def test_data_uri_parser_rejects_active_or_malformed_content(self):
        svg = base64.b64encode(b"<svg><script>x</script></svg>").decode("ascii")
        with self.assertRaises(ValueError):
            normalize_customer_logo_data_uri(f"data:image/svg+xml;base64,{svg}")
        with self.assertRaises(ValueError):
            normalize_customer_logo_data_uri("data:image/png;base64,not base64")
        with self.assertRaisesRegex(ValueError, "512KB"):
            normalize_customer_logo_data_uri(
                "data:image/png;base64," + "A" * (MAX_CUSTOMER_LOGO_BYTES * 2)
            )
        with self.assertRaises(ValueError):
            normalize_customer_logo_data_uri({"src": "unexpected"})


class CustomerLogoSnapshotTests(unittest.TestCase):
    def test_logo_is_snapshotted_and_rendered_inside_standalone_html(self):
        logo = validate_customer_logo(_png_header(320, 120), "image/png")
        customer = CustomerProfile(
            customer_id="customer-one",
            customer_name="Customer One",
            logo_data_uri=logo.data_uri,
        )
        report = ReportResult(
            period={
                "period_type": "day",
                "start_dt": "2026-08-01 00:00:00",
                "end_dt": "2026-08-01 23:59:59",
                "file_suffix": "20260801_20260801",
            },
            customer=customer.to_dict(),
        )

        snapshot = report.to_dict()
        restored = ReportResult.from_dict(snapshot)
        html = HtmlReportRenderer().render(restored)

        self.assertEqual(
            snapshot["customer"]["logo_data_uri"],
            logo.data_uri,
        )
        self.assertIn(f'src="{logo.data_uri}"', html)
        self.assertIn('class="customer-logo-plate"', html)
        self.assertIn("object-fit: contain", html)

    def test_invalid_snapshot_logo_falls_back_to_escaped_initials(self):
        report = ReportResult(
            period={
                "period_type": "day",
                "start_dt": "2026-08-01 00:00:00",
                "end_dt": "2026-08-01 23:59:59",
                "file_suffix": "20260801_20260801",
            },
            customer={
                "name": "Customer <script>",
                "logo_data_uri": "data:image/svg+xml,<script>alert(1)</script>",
            },
        )

        html = HtmlReportRenderer().render(report)

        self.assertNotIn("<script>", html)
        self.assertIn("Customer &lt;script&gt;", html)
        self.assertIn(">CS</span>", html)
        self.assertNotIn("logo_data_uri", report.to_dict()["customer"])


if __name__ == "__main__":
    unittest.main()
