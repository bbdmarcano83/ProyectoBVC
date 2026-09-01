import unittest

from services.fundamental_trend_v5 import compute_fundamental_trend, comparable_usd_value


class FundamentalTrendV5Tests(unittest.TestCase):
    def test_ves_without_usd_view_is_not_comparable(self):
        self.assertIsNone(comparable_usd_value({"currency":"VES","equity":100}, "equity"))

    def test_usd_normalized_series_can_be_mejorando(self):
        history = [
            {"as_of":"2024-12-31","currency":"VES","equity_usd":100,"revenue_usd":100,"net_income_usd":10,"total_assets_usd":150},
            {"as_of":"2025-12-31","currency":"VES","equity_usd":120,"revenue_usd":130,"net_income_usd":14,"total_assets_usd":170},
        ]
        out = compute_fundamental_trend(history)
        self.assertEqual(out["label"], "MEJORANDO")
        self.assertGreater(out["coverage_pct"], 0)
        self.assertEqual(out["changes"]["equity"], 20.0)

    def test_usd_normalized_series_can_be_deteriorando(self):
        history = [
            {"as_of":"2024-12-31","currency":"VES","equity_usd":100,"revenue_usd":100,"net_income_usd":10,"total_assets_usd":150},
            {"as_of":"2025-12-31","currency":"VES","equity_usd":80,"revenue_usd":70,"net_income_usd":5,"total_assets_usd":120},
        ]
        out = compute_fundamental_trend(history)
        self.assertEqual(out["label"], "DETERIORANDO")

    def test_one_period_is_insufficient(self):
        out = compute_fundamental_trend([{"as_of":"2025-12-31","equity_usd":100}])
        self.assertEqual(out["label"], "SIN HISTORIA SUFICIENTE")
        self.assertEqual(out["coverage_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
