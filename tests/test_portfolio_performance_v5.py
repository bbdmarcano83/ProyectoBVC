import unittest
from datetime import date

from services.portfolio_performance_v5 import modified_dietz_return, analyze_snapshot_performance, max_drawdown


class PortfolioPerformanceV5Tests(unittest.TestCase):
    def test_contribution_is_not_counted_as_return(self):
        # 100 inicial + aporte 100 a mitad; termina 200 => 0% retorno económico.
        r = modified_dietz_return(
            100, 200, date(2026, 1, 1), date(2026, 1, 31),
            [(date(2026, 1, 16), 100)],
        )
        self.assertAlmostEqual(r, 0.0, places=6)

    def test_withdrawal_is_not_counted_as_loss(self):
        # 200 inicial - retiro 100; termina 100 => 0% retorno económico.
        r = modified_dietz_return(
            200, 100, date(2026, 1, 1), date(2026, 1, 31),
            [(date(2026, 1, 16), -100)],
        )
        self.assertAlmostEqual(r, 0.0, places=6)

    def test_snapshot_analysis_exposes_windows_and_drawdown(self):
        snaps = [
            {"as_of": "2026-01-02", "total_market_bs": 100, "total_market_usd": 10, "fx_bcv": 10},
            {"as_of": "2026-03-01", "total_market_bs": 120, "total_market_usd": 11, "fx_bcv": 10.9},
            {"as_of": "2026-06-01", "total_market_bs": 110, "total_market_usd": 9, "fx_bcv": 12.2},
            {"as_of": "2026-09-01", "total_market_bs": 150, "total_market_usd": 12, "fx_bcv": 12.5},
        ]
        out = analyze_snapshot_performance(snaps, [], as_of=date(2026, 9, 1))
        self.assertTrue(out["available"])
        self.assertIn("6M", out["windows"])
        self.assertIsNotNone(out["max_drawdown_bs_pct"])
        self.assertIsNotNone(out["max_drawdown_usd_observed_pct"])
        self.assertFalse(out["windows"]["1Y"]["available"])

    def test_ibc_window_receives_same_midperiod_contribution(self):
        snaps = [
            {"as_of": "2026-01-01", "total_market_bs": 100, "total_market_usd": 10, "fx_bcv": 10},
            {"as_of": "2026-02-01", "total_market_bs": 220, "total_market_usd": 20, "fx_bcv": 11},
        ]
        tx = [{
            "fecha": "2026-01-16", "tipo": "compra", "cantidad": 1, "precio": 100,
            "neto": 100, "tasa_bcv": 10,
        }]
        ibc = [
            {"date": "2026-01-01", "close": 100},
            {"date": "2026-01-16", "close": 105},
            {"date": "2026-02-01", "close": 110},
        ]
        out = analyze_snapshot_performance(snaps, tx, ibc_points=ibc, as_of=date(2026, 2, 1))
        w = out["windows"]["1M"]
        self.assertTrue(w["available"])
        self.assertIsNotNone(w["ibc_return_bs_pct"])
        self.assertIsNotNone(w["alpha_bs_pp"])
        # Si el aporte se tratara como rentabilidad, el retorno de cartera sería 120%; no debe serlo.
        self.assertLess(w["return_bs_pct"], 20.0)

    def test_ytd_is_unavailable_when_history_starts_after_year_start(self):
        snaps = [
            {"as_of": "2026-03-01", "total_market_bs": 100},
            {"as_of": "2026-09-01", "total_market_bs": 140},
        ]
        out = analyze_snapshot_performance(snaps, [], as_of=date(2026, 9, 1))
        ytd = out["windows"]["YTD"]
        self.assertFalse(ytd["available"])
        self.assertEqual(ytd["reason"], "sin_historia_suficiente")
        self.assertEqual(ytd["required_start_date"], "2026-01-01")
        self.assertEqual(ytd["first_snapshot_date"], "2026-03-01")

    def test_previous_snapshot_before_target_is_valid_for_window(self):
        snaps = [
            {"as_of": "2026-05-30", "total_market_bs": 100},
            {"as_of": "2026-06-15", "total_market_bs": 110},
            {"as_of": "2026-07-01", "total_market_bs": 120},
        ]
        out = analyze_snapshot_performance(snaps, [], as_of=date(2026, 7, 1))
        one_month = out["windows"]["1M"]  # target 2026-05-31
        self.assertTrue(one_month["available"])
        self.assertEqual(one_month["start_date"], "2026-05-30")

    def test_drawdown(self):
        self.assertAlmostEqual(max_drawdown([100, 120, 90, 130]), -25.0)


if __name__ == "__main__":
    unittest.main()
