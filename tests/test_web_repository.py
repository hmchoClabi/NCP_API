import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from webapp.repository import _remove_local_report_artifacts


class ReportArtifactCleanupTests(unittest.TestCase):
    def test_cleanup_only_removes_local_files_below_output_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_root = root / "output"
            output_root.mkdir()
            report_file = output_root / "report.html"
            outside_file = root / "outside.html"
            report_file.write_text("report", encoding="utf-8")
            outside_file.write_text("outside", encoding="utf-8")

            with patch.dict(os.environ, {"REPORT_OUTPUT_DIR": str(output_root)}):
                removed, failed = _remove_local_report_artifacts([
                    report_file.as_uri(),
                    outside_file.as_uri(),
                    "s3://archive/report.html",
                ])

            self.assertEqual((removed, failed), (1, 0))
            self.assertFalse(report_file.exists())
            self.assertTrue(outside_file.exists())


if __name__ == "__main__":
    unittest.main()
