import unittest
from datetime import date

from services.fx_history_v5 import (
    parse_official_history,
    close_rate_from_records,
    calendar_average_from_records,
    infer_period_start,
)


class FxHistoryV5Tests(unittest.TestCase):
    def setUp(self):
        self.records = [
            (date(2026, 1, 2), 100.0),
            (date(2026, 1, 5), 110.0),
            (date(2026, 1, 6), 120.0),
        ]

    def test_parse_history_discards_invalid_and_deduplicates(self):
        payload = [
            {"fecha": "2026-01-02", "promedio": 100},
            {"fecha": "2026-01-02", "promedio": 101},
            {"fecha": "bad", "promedio": 999},
            {"fecha": "2026-01-03", "promedio": 0},
        ]
        out = parse_official_history(payload)
        self.assertEqual(out, [(date(2026, 1, 2), 101.0)])

    def test_close_uses_last_published_rate_on_weekend(self):
        self.assertEqual(close_rate_from_records(self.records, "2026-01-04"), 100.0)
        self.assertEqual(close_rate_from_records(self.records, "2026-01-05"), 110.0)

    def test_calendar_average_forward_fills_non_publishing_days(self):
        # Jan 2,3,4 = 100; Jan 5 = 110; Jan 6 = 120 => 530 / 5 = 106
        avg = calendar_average_from_records(self.records, "2026-01-02", "2026-01-06")
        self.assertEqual(avg, 106.0)

    def test_no_prior_rate_means_no_average(self):
        self.assertIsNone(calendar_average_from_records(self.records, "2026-01-01", "2026-01-01"))

    def test_period_start_inference(self):
        self.assertEqual(infer_period_start("2026-Q2", "2026-06-30"), "2026-04-01")
        self.assertEqual(infer_period_start("FY2025", "2025-12-31"), "2025-01-01")
        self.assertEqual(infer_period_start("2025-H2", "2025-12-31"), "2025-07-01")
        self.assertIsNone(infer_period_start("rolling", "2025-12-31"))


if __name__ == "__main__":
    unittest.main()
