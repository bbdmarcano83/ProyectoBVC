import unittest
from datetime import date

from services.v5_routes import snapshot_capture_policy


class V5SnapshotCapturePolicyTests(unittest.TestCase):
    def test_intraday_never_persists_daily_snapshot(self):
        out = snapshot_capture_policy(
            valuation_day=date(2026, 9, 1),
            ibc_day=date(2026, 9, 1),
            market_is_open=True,
        )
        self.assertFalse(out["capture"])
        self.assertEqual(out["reason"], "market_intraday")

    def test_stale_ibc_terminal_never_persists_snapshot(self):
        out = snapshot_capture_policy(
            valuation_day=date(2026, 9, 1),
            ibc_day=date(2026, 8, 31),
            market_is_open=False,
        )
        self.assertFalse(out["capture"])
        self.assertEqual(out["reason"], "terminal_date_mismatch")
        self.assertEqual(out["valuation_as_of"], "2026-09-01")
        self.assertEqual(out["ibc_as_of"], "2026-08-31")

    def test_missing_ibc_never_persists_snapshot(self):
        out = snapshot_capture_policy(
            valuation_day=date(2026, 9, 1),
            ibc_day=None,
            market_is_open=False,
        )
        self.assertFalse(out["capture"])
        self.assertEqual(out["reason"], "ibc_terminal_missing")

    def test_closed_aligned_market_can_persist_snapshot(self):
        out = snapshot_capture_policy(
            valuation_day=date(2026, 9, 1),
            ibc_day=date(2026, 9, 1),
            market_is_open=False,
        )
        self.assertTrue(out["capture"])
        self.assertIsNone(out["reason"])
        self.assertEqual(out["as_of"], "2026-09-01")


if __name__ == "__main__":
    unittest.main()
