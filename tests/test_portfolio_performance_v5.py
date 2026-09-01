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
            {"as_of": "2026-01-02", "total_market_bs": 100, "total_market_usd": 10},
            {"as_of": "2026-03-01", "total_market_bs": 120, "total_market_usd": 11},
            {"as_of": "2026-06-01", "total_market_bs": 110, "total_market_usd": 9},
            {"as_of": "2026-09-01", "total_market_bs": 150, "total_market_usd": 12},
        ]
        out = analyze_snapshot_performance(snaps, [], as_of=date(2026, 9, 1))
        self.assertTrue(out["available"])
        self.assertIn("6M", out["windows"])
        self.assertIsNotNone(out["max_drawdown_bs_pct"])
        self.assertIsNotNone(out["max_drawdown_usd_observed_pct"])

    def test_drawdown(self):
        self.assertAlmostEqual(max_drawdown([100, 120, 90, 130]), -25.0)


if __name__ == "__main__":
    unittest.main()
