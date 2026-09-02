import unittest
from datetime import date
from unittest.mock import patch

from services.fx_history_v5 import (
    parse_official_history,
    close_rate_from_records,
    calendar_average_from_records,
    infer_period_start,
    coverage_bounds,
    records_cover_target,
    get_close_rate,
    get_period_average,
    attach_historical_bcv_fx,
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
        avg = calendar_average_from_records(self.records, "2026-01-02", "2026-01-06")
        self.assertEqual(avg, 106.0)

    def test_no_prior_rate_means_no_average(self):
        self.assertIsNone(calendar_average_from_records(self.records, "2026-01-01", "2026-01-01"))

    def test_coverage_bounds_are_explicit(self):
        self.assertEqual(coverage_bounds(self.records), (date(2026, 1, 2), date(2026, 1, 6)))
        self.assertEqual(coverage_bounds([]), (None, None))

    def test_short_non_publishing_gap_is_allowed_but_stale_cache_is_not(self):
        self.assertTrue(records_cover_target(self.records, "2026-01-10"))
        self.assertFalse(records_cover_target(self.records, "2026-01-20"))

    def test_get_close_rate_fails_closed_when_refresh_cannot_cover_target(self):
        with patch("services.fx_history_v5._load_records", return_value=self.records), \
             patch("services.fx_history_v5.refresh_history", return_value={"ok": False}):
            self.assertIsNone(get_close_rate("2026-02-01", refresh_if_missing=True))

    def test_period_average_never_forward_fills_weeks_beyond_cache(self):
        with patch("services.fx_history_v5._load_records", return_value=self.records), \
             patch("services.fx_history_v5.refresh_history", return_value={"ok": False}):
            self.assertIsNone(get_period_average("2026-01-02", "2026-02-01", refresh_if_missing=True))

    def test_period_start_inference(self):
        self.assertEqual(infer_period_start("2026-Q2", "2026-06-30"), "2026-04-01")
        self.assertEqual(infer_period_start("FY2025", "2025-12-31"), "2025-01-01")
        self.assertEqual(infer_period_start("2025-H2", "2025-12-31"), "2025-07-01")
        self.assertIsNone(infer_period_start("rolling", "2025-12-31"))

    def test_verified_point_fallback_resolves_sivensa_2022_close_only_when_primary_missing(self):
        data = {"currency": "VES", "monetary_basis": "constant_ves_end_period", "total_assets": 100}
        with patch("services.fx_history_v5.get_close_rate", return_value=None):
            out, meta = attach_historical_bcv_fx(
                data, as_of="2022-09-30", fiscal_period="FY2022", refresh_if_missing=False
            )
        self.assertTrue(meta["ok"])
        self.assertEqual(out["fx_rate_bcv_close"], 8.2036)
        self.assertEqual(meta["fallback_rate_date"], "2022-09-30")
        self.assertEqual(meta["source_kind"], "crosschecked_secondary_history")
        self.assertIn("close_point", meta["fallback_components"])

    def test_new_verified_fiscal_closes_resolve_exactly(self):
        verified = {
            "2022-08-31": 7.8922,
            "2022-10-31": 8.5918,
            "2022-11-30": 11.079,
            "2023-02-28": 24.361,
        }
        for as_of, expected in verified.items():
            with self.subTest(as_of=as_of), patch("services.fx_history_v5.get_close_rate", return_value=None):
                out, meta = attach_historical_bcv_fx(
                    {"currency": "VES", "monetary_basis": "constant_ves_end_period", "total_assets": 100},
                    as_of=as_of,
                    fiscal_period=f"FY{as_of[:4]}",
                    refresh_if_missing=False,
                )
            self.assertTrue(meta["ok"])
            self.assertEqual(out["fx_rate_bcv_close"], expected)
            self.assertEqual(meta["fallback_rate_date"], as_of)
            self.assertEqual(meta["source_kind"], "crosschecked_secondary_history")

    def test_verified_point_fallback_uses_last_publication_for_weekend_2023_close(self):
        data = {"currency": "VES", "monetary_basis": "constant_ves_end_period", "total_assets": 100}
        with patch("services.fx_history_v5.get_close_rate", return_value=None):
            out, meta = attach_historical_bcv_fx(
                data, as_of="2023-09-30", fiscal_period="FY2023", refresh_if_missing=False
            )
        self.assertTrue(meta["ok"])
        self.assertEqual(out["fx_rate_bcv_close"], 34.425)
        self.assertEqual(meta["fallback_rate_date"], "2023-09-29")

    def test_point_fallback_is_not_generalized_to_unverified_date(self):
        data = {"currency": "VES", "monetary_basis": "constant_ves_end_period", "total_assets": 100}
        with patch("services.fx_history_v5.get_close_rate", return_value=None):
            out, meta = attach_historical_bcv_fx(
                data, as_of="2022-08-30", fiscal_period="FY2022", refresh_if_missing=False
            )
        self.assertFalse(meta["ok"])
        self.assertNotIn("fx_rate_bcv_close", out)
        self.assertEqual(meta["fallback_components"], [])

    def test_primary_rate_has_priority_over_verified_point_fallback(self):
        data = {"currency": "VES", "monetary_basis": "constant_ves_end_period", "total_assets": 100}
        with patch("services.fx_history_v5.get_close_rate", return_value=8.25):
            out, meta = attach_historical_bcv_fx(
                data, as_of="2022-09-30", fiscal_period="FY2022", refresh_if_missing=False
            )
        self.assertTrue(meta["ok"])
        self.assertEqual(out["fx_rate_bcv_close"], 8.25)
        self.assertEqual(meta["source_kind"], "bcv_derived_api")
        self.assertEqual(meta["fallback_components"], [])


if __name__ == "__main__":
    unittest.main()
