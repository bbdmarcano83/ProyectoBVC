import unittest

from services.fundamental_history_v5 import build_series_from_records


class FundamentalHistoryV5Tests(unittest.TestCase):
    def test_quarters_are_not_mixed_with_annual_series(self):
        records = [
            {"as_of":"2025-03-31","fiscal_period":"2025-Q1","document_type":"quarterly_report","validation_score":100,"snapshot_id":1,"data":{"currency":"VES","net_income_usd":2}},
            {"as_of":"2025-12-31","fiscal_period":"FY2025","document_type":"annual_audited_financial_statements","validation_score":100,"snapshot_id":2,"data":{"currency":"VES","net_income_usd":10}},
            {"as_of":"2026-12-31","fiscal_period":"FY2026","document_type":"annual_audited_financial_statements","validation_score":100,"snapshot_id":3,"data":{"currency":"VES","net_income_usd":12}},
        ]
        out = build_series_from_records(records)
        self.assertEqual(out["earnings_history_usd"], [10.0, 12.0])
        self.assertEqual(out["earnings_history_usd_dates"], ["2025-12-31", "2026-12-31"])
        self.assertEqual(out["history_periods_usd"], 2)

    def test_raw_ves_is_never_used_or_counted_cross_period(self):
        records = [
            {"as_of":"2025-12-31","fiscal_period":"FY2025","document_type":"annual_report","validation_score":100,"snapshot_id":1,"data":{"currency":"VES","net_income":100}},
            {"as_of":"2026-12-31","fiscal_period":"FY2026","document_type":"annual_report","validation_score":100,"snapshot_id":2,"data":{"currency":"VES","net_income":500}},
        ]
        out = build_series_from_records(records)
        self.assertNotIn("earnings_history_usd", out)
        self.assertEqual(out["history_periods_usd"], 0)
        self.assertEqual(out["history_dates_usd"], [])

    def test_unusable_annual_period_does_not_inflate_history_count(self):
        records = [
            {"as_of":"2024-12-31","fiscal_period":"FY2024","document_type":"annual_report","validation_score":100,"snapshot_id":1,"data":{"currency":"VES","net_income":100}},
            {"as_of":"2025-12-31","fiscal_period":"FY2025","document_type":"annual_report","validation_score":100,"snapshot_id":2,"data":{"currency":"VES","net_income_usd":10}},
        ]
        out = build_series_from_records(records)
        self.assertEqual(out["history_periods_usd"], 1)
        self.assertEqual(out["history_dates_usd"], ["2025-12-31"])
        self.assertEqual(out["earnings_history_usd"], [10.0])

    def test_reported_usd_can_be_used_without_conversion(self):
        records = [
            {"as_of":"2025-12-31","fiscal_period":"FY2025","document_type":"annual_report","validation_score":90,"snapshot_id":1,"data":{"currency":"USD","revenue":20}},
            {"as_of":"2026-12-31","fiscal_period":"FY2026","document_type":"annual_report","validation_score":90,"snapshot_id":2,"data":{"currency":"USD","revenue":25}},
        ]
        out = build_series_from_records(records)
        self.assertEqual(out["revenue_history_usd"], [20.0, 25.0])
        self.assertEqual(out["history_periods_usd"], 2)

    def test_duplicate_date_prefers_higher_validation(self):
        records = [
            {"as_of":"2025-12-31","fiscal_period":"FY2025","document_type":"annual_report","validation_score":80,"snapshot_id":1,"data":{"currency":"VES","equity_usd":10}},
            {"as_of":"2025-12-31","fiscal_period":"FY2025","document_type":"annual_audited_financial_statements","validation_score":100,"snapshot_id":2,"data":{"currency":"VES","equity_usd":12}},
        ]
        out = build_series_from_records(records)
        self.assertEqual(out["equity_history_usd"], [12.0])
        self.assertEqual(out["history_periods_usd"], 1)


if __name__ == "__main__":
    unittest.main()
