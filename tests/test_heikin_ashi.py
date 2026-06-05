import unittest

import pandas as pd

from data_collection.heikin_ashi import add_heikin_ashi_columns


class HeikinAshiTest(unittest.TestCase):
    def test_adds_expected_heikin_ashi_columns(self) -> None:
        df = pd.DataFrame(
            {
                "open": [10.0, 12.0],
                "high": [13.0, 14.0],
                "low": [9.0, 11.0],
                "close": [12.0, 13.0],
            }
        )

        result = add_heikin_ashi_columns(df)

        self.assertEqual(result["ha_open"].tolist(), [11.0, 11.0])
        self.assertEqual(result["ha_close"].tolist(), [11.0, 12.5])
        self.assertEqual(result["ha_high"].tolist(), [13.0, 14.0])
        self.assertEqual(result["ha_low"].tolist(), [9.0, 11.0])


if __name__ == "__main__":
    unittest.main()
