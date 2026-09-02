import unittest

from services.fx_normalization_v5 import normalize_to_usd, validate_fx_metadata, prefer_usd
from services.scoring_engine_v5 import _v5_signal


class FXNormalizationV5Tests(unittest.TestCase):
    def test_nominal_ves_uses_close_for_balance_and_average_for_flows(self):
        data = {
            "currency": "VES",
            "monetary_basis": "nominal_ves",
            "fx_rate_bcv_close": 200.0,
            "fx_rate_bcv_avg": 100.0,
            "fx_source_url": "https://www.bcv.org.ve/",
            "fx_as_of": "2026-06-30",
            "total_assets": 2000.0,
            "equity": 1000.0,
            "net_income": 500.0,
        }
        out, meta = normalize_to_usd(data)
        self.assertTrue(meta["valid"])
        self.assertEqual(out["total_assets_usd"], 10.0)
        self.assertEqual(out["equity_usd"], 5.0)
        self.assertEqual(out["net_income_usd"], 5.0)
        self.assertEqual(out["fx_normalization_method_v5"], "bcv_close_balance_avg_flows+valuation_fx_market")

    def test_constant_ves_uses_close_rate_for_reexpressed_flows(self):
        data = {
            "currency": "VES",
            "monetary_basis": "constant_ves_end_period",
            "fx_rate_bcv_close": 250.0,
            "fx_source_url": "https://www.bcv.org.ve/",
            "fx_as_of": "2025-12-31",
            "total_assets": 2500.0,
            "net_income": 500.0,
        }
        out, meta = normalize_to_usd(data)
        self.assertTrue(meta["valid"])
        self.assertEqual(out["total_assets_usd"], 10.0)
        self.assertEqual(out["net_income_usd"], 2.0)
        self.assertEqual(out["fx_normalization_method_v5"], "bcv_close_all_constant_ves+valuation_fx_market")

    def test_missing_historical_fx_fails_closed(self):
        meta = validate_fx_metadata({"currency": "VES", "monetary_basis": "nominal_ves"})
        self.assertFalse(meta["valid"])
        self.assertIn("missing_bcv_close_rate", meta["flags"])
        self.assertIn("missing_bcv_average_rate", meta["flags"])

    def test_current_market_price_does_not_use_statement_close_fx(self):
        data = {
            "currency": "VES",
            "monetary_basis": "constant_ves_end_period",
            "fx_rate_bcv_close": 50.0,
            "fx_source_url": "https://www.bcv.org.ve/",
            "fx_as_of": "2024-12-31",
            "nav_per_share": 500.0,
            "market_price": 900.0,
        }
        out, meta = normalize_to_usd(data)
        self.assertEqual(out["nav_per_share_usd"], 10.0)
        self.assertNotIn("market_price_usd", out)
        self.assertIsNone(prefer_usd(out, "market_price"))
        self.assertFalse(meta["valid"])
        self.assertIn("missing_market_bcv_rate", meta["flags"])
        self.assertIn("missing_valuation_as_of", meta["flags"])

    def test_market_price_uses_explicit_valuation_fx(self):
        data = {
            "currency": "VES",
            "monetary_basis": "constant_ves_end_period",
            "fx_rate_bcv_close": 50.0,
            "fx_source_url": "https://www.bcv.org.ve/",
            "fx_as_of": "2024-12-31",
            "nav_per_share": 500.0,
            "market_price": 900.0,
            "valuation_as_of": "2026-09-01",
            "market_fx_rate_bcv": 600.0,
            "market_fx_source_url": "https://www.bcv.org.ve/",
        }
        out, meta = normalize_to_usd(data)
        self.assertTrue(meta["valid"])
        self.assertEqual(out["nav_per_share_usd"], 10.0)
        self.assertEqual(out["market_price_usd"], 1.5)
        self.assertEqual(out["valuation_as_of_v5"], "2026-09-01")
        self.assertTrue(out["market_fx_valid_v5"])

    def test_v5_confirmation_is_blocked_when_fx_pending(self):
        row = {
            "fundamental_score_v5": 90,
            "fundamental_coverage_v5": 100,
            "fx_valid_v5": False,
            "fx_flags_v5": ["missing_bcv_close_rate"],
            "strength_score_v3": 90,
            "opportunity_score_v3": 90,
            "confidence_score_v3": 90,
            "risk_score_v3": 10,
            "data_quality_ok_v3": True,
        }
        stage, _ = _v5_signal(row)
        self.assertEqual(stage, "FUNDAMENTALES · FX PENDIENTE")


if __name__ == "__main__":
    unittest.main()
