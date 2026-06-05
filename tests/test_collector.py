import tempfile
import unittest
from pathlib import Path

import pandas as pd

from data_collection.collector import CollectionRequest, MarketDataCollector


class FakeClient:
    def get_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        start: str | None = None,
        end: str | None = None,
        period: str | None = None,
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "symbol": [symbol.upper()],
                "timeframe": [timeframe],
                "date": ["2026-01-01"],
                "open": [10.0],
                "high": [11.0],
                "low": [9.0],
                "close": [10.5],
                "volume": [1000],
            }
        )


class MarketDataCollectorTest(unittest.TestCase):
    def test_collect_writes_csv_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            collector = MarketDataCollector(client=FakeClient())
            request = CollectionRequest(
                symbols=["aapl"],
                timeframes=["1d"],
                period="5d",
                output_dir=output_dir,
                include_heikin_ashi=True,
            )

            results = collector.collect(request)
            csv_path = output_dir / "AAPL" / "1d.csv"

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].rows, 1)
            self.assertTrue(csv_path.exists())
            self.assertTrue((output_dir / "manifest.json").exists())

            exported = pd.read_csv(csv_path)
            self.assertIn("ha_open", exported.columns)
            self.assertIn("ha_close", exported.columns)


if __name__ == "__main__":
    unittest.main()
