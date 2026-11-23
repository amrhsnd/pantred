import csv
from datetime import datetime, timezone
import hashlib
import io
import unittest
import zipfile

from scripts.fetch_binance import FIELDS, parse_archive


class BinanceArchiveTest(unittest.TestCase):
    day = datetime(2026, 10, 24, tzinfo=timezone.utc)
    filename = "BTCUSDT-5m-2026-10-24.zip"

    def rows(self, microseconds=True):
        factor = 1000 if microseconds else 1
        start = int(self.day.timestamp()) * 1000
        return [
            [str((start + index * 300_000) * factor), "100.12345678", "102", "99",
             "101", "3.5", str((start + (index + 1) * 300_000) * factor - 1),
             "350", "8", "1.5", "150", "0"]
            for index in range(288)
        ]

    def archive(self, rows):
        text = io.StringIO()
        csv.writer(text).writerows(rows)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(self.filename.removesuffix(".zip") + ".csv", text.getvalue())
        payload = buffer.getvalue()
        checksum = f"{hashlib.sha256(payload).hexdigest()}  {self.filename}\n".encode()
        return payload, checksum

    def parse(self, rows):
        return parse_archive(*self.archive(rows), self.filename, "BTCUSDT", "5m", self.day)[0]

    def test_microsecond_archives_keep_precision_and_full_day(self):
        rows = self.parse(self.rows())
        self.assertEqual(len(rows), 288)
        first, last = dict(zip(FIELDS, rows[0])), dict(zip(FIELDS, rows[-1]))
        self.assertEqual(first["datetime"], "2026-10-24T00:00:00+00:00")
        self.assertEqual(first["open_time_ms"], int(self.day.timestamp()) * 1000)
        self.assertEqual(first["close_time_ms"] - first["open_time_ms"], 299_999)
        self.assertEqual(first["open"], "100.12345678")
        self.assertEqual(last["datetime"], "2026-10-24T23:55:00+00:00")

    def test_legacy_millisecond_archives_match_microseconds(self):
        self.assertEqual(self.parse(self.rows(False)), self.parse(self.rows(True)))

    def test_checksum_tampering_is_rejected(self):
        payload, checksum = self.archive(self.rows())
        with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
            parse_archive(payload + b"tampered", checksum, self.filename, "BTCUSDT", "5m", self.day)

    def test_missing_and_duplicate_candles_are_rejected(self):
        for mode in ("missing", "duplicate", "truncated"):
            with self.subTest(mode=mode):
                rows = self.rows()
                if mode == "missing":
                    del rows[120]
                elif mode == "duplicate":
                    rows[120] = rows[119]
                else:
                    rows.pop()
                with self.assertRaises(ValueError):
                    self.parse(rows)

    def test_invalid_prices_and_volumes_are_rejected(self):
        for column, value in ((2, "98"), (5, "-1"), (8, "-1"), (9, "4"), (4, "NaN")):
            with self.subTest(column=column, value=value):
                rows = self.rows()
                rows[42][column] = value
                with self.assertRaises(ValueError):
                    self.parse(rows)

    def test_wrong_candle_close_boundary_is_rejected(self):
        rows = self.rows()
        rows[-1][6] = str(int(rows[-1][6]) + 1000)
        with self.assertRaisesRegex(ValueError, "misaligned"):
            self.parse(rows)


if __name__ == "__main__":
    unittest.main()
