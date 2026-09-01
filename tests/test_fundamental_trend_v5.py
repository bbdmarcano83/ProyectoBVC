import unittest

from services.fundamental_history_v5 import build_series_from_records
from services.fundamental_trend_v5 import (
    comparable_usd_value,
    compute_fundamental_trend,
    compute_fundamental_trend_from_series,
)


class FundamentalTrendV5Tests(unittest.TestCase):
    def test_ves_without_usd_view_is_not_comparable(self):
        self.assertIsNone(comparable_usd_value({"currency": "VES", "equity": 100}, "equity"))

    def test_usd_normalized_series_can_be_mejorando(self):
        history = [
            {"as_of": "2024-12-31", "currency": "VES", "equity_usd": 100, "revenue_usd": 100, "net_income_usd": 10, "total_assets_usd": 150},
            {"as_of": "2025-12-31", "currency": "VES", "equity_usd": 120, "revenue_usd": 130, "net_income_usd": 14, "total_assets_usd": 170},
        ]
        out = compute_fundamental_trend(history)
        self.assertEqual(out["label"], "MEJORANDO")
        self.assertGreater(out["coverage_pct"], 0)
        self.assertEqual(out["changes"]["equity"], 20.0)

    def test_usd_normalized_series_can_be_deteriorando(self):
        history = [
            {"as_of": "2024-12-31", "currency": "VES", "equity_usd": 100, "revenue_usd": 100, "net_income_usd": 10, "total_assets_usd": 150},
            {"as_of": "2025-12-31", "currency": "VES", "equity_usd": 80, "revenue_usd": 70, "net_income_usd": 5, "total_assets_usd": 120},
        ]
        out = compute_fundamental_trend(history)
        self.assertEqual(out["label"], "DETERIORANDO")

    def test_one_period_is_insufficient(self):
        out = compute_fundamental_trend([{"as_of": "2025-12-31", "equity_usd": 100}])
        self.assertEqual(out["label"], "SIN HISTORIA SUFICIENTE")
        self.assertEqual(out["coverage_pct"], 0.0)

    def test_production_series_excludes_quarterly_snapshot(self):
        records = [
            {
                "as_of": "2024-12-31",
                "fiscal_period": "FY2024",
                "document_type": "annual_audited",
                "validation_score": 100,
                "snapshot_id": 1,
                "data": {"currency": "VES", "equity_usd": 100, "net_income_usd": 10, "total_assets_usd": 150},
            },
            {
                "as_of": "2025-12-31",
                "fiscal_period": "FY2025",
                "document_type": "annual_audited",
                "validation_score": 100,
                "snapshot_id": 2,
                "data": {"currency": "VES", "equity_usd": 120, "net_income_usd": 14, "total_assets_usd": 170},
            },
            {
                "as_of": "2026-06-30",
                "fiscal_period": "2026-Q2",
                "document_type": "quarterly_report",
                "validation_score": 100,
                "snapshot_id": 3,
                "data": {"currency": "VES", "equity_usd": 20, "net_income_usd": 1, "total_assets_usd": 30},
            },
        ]
        series = build_series_from_records(records)
        self.assertEqual(series["history_periods_usd"], 2)
        self.assertEqual(series["history_dates_usd"], ["2024-12-31", "2025-12-31"])

        trend = compute_fundamental_trend_from_series(series, "financial")
        self.assertEqual(trend["periods"], 2)
        self.assertEqual(trend["latest_as_of"], "2025-12-31")
        self.assertEqual(trend["label"], "MEJORANDO")

    def test_financial_coverage_does_not_require_revenue_fcf_or_nav(self):
        series = {
            "history_basis_v5": "annual_comparable_usd_only",
            "history_dates_usd": ["2024-12-31", "2025-12-31"],
            "history_periods_usd": 2,
            "equity_history_usd": [100, 120],
            "equity_history_usd_dates": ["2024-12-31", "2025-12-31"],
            "earnings_history_usd": [10, 12],
            "earnings_history_usd_dates": ["2024-12-31", "2025-12-31"],
            "assets_history_usd": [150, 180],
            "assets_history_usd_dates": ["2024-12-31", "2025-12-31"],
        }
        trend = compute_fundamental_trend_from_series(series, "financial")
        self.assertEqual(trend["coverage_pct"], 100.0)
        self.assertEqual(set(trend["changes"]), {"equity", "net_income", "total_assets"})


if __name__ == "__main__":
    unittest.main()
