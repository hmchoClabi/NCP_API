import unittest

from utils.data_utils import get_unix_time_stamp


class DataUtilsTests(unittest.TestCase):
    def test_kst_timestamp_conversion_is_explicit(self):
        self.assertEqual(
            get_unix_time_stamp("1970-01-01 09:00:00"),
            0,
        )


if __name__ == "__main__":
    unittest.main()
