import os
import unittest
from unittest.mock import patch

from services.fundamentals_v5 import compute_metrics, enrich_fundamental_scores
from services.scoring_engine_v5 import _v5_signal, apply_v5


class FundamentalMetricsV5Tests(unittest.TestCase):
    def test_non_financial_greenblatt_metrics_are_computed_from_supplied_data(self):
        data = {
            "industry_type": "non_financial",
            "market_cap": 1000,
            "total_debt": 200,
            "cash": 100,
            "ebit": 165,
            "current_assets": 500,
            "current_liabilities": 300,
            "net_ppe": 350,
            "net_income": 120,
            "equity": 600,
            "total_assets": 1400,
            "revenue": 900,
            "free_cash_flow": 100,
        }
        m = compute_metrics(data, "Industrial")
        self.assertEqual(m["industry_type_v5"], "non_financial")
        self.assertAlmostEqual(m["enterprise_value_v5"], 1100)
        self.assertAlmostEqual(m["earnings_yield_pct_v5"], 15.0)
        self.assertAlmostEqual(m["return_on_capital_pct_v5"], 30.0)

    def test_financials_use_dedicated_path(self):
        data = {
            "industry_type": "financial",
            "market_cap": 800,
            "net_income": 80,
            "equity": 400,
            "total_assets": 4000,
        }
        m = compute_metrics(data, "Bancos")
        self.assertEqual(m["industry_type_v5"], "financial")
        self.assertIsNone(m["return_on_capital_pct_v5"])
        self.assertAlmostEqual(m["roe_pct_v5"], 20.0)
        self.assertAlmostEqual(m["roa_pct_v5"], 2.0)
        self.assertAlmostEqual(m["pb_v5"], 2.0)
        self.assertAlmostEqual(m["pe_v5"], 10.0)

    def test_missing_fundamentals_are_not_imputed(self):
        with patch.dict(os.environ, {}, clear=True):
            rows, meta = enrich_fundamental_scores([{"simbolo": "AAA", "sector": "Industrial"}])
        self.assertFalse(rows[0]["fundamentals_available_v5"])
        self.assertNotIn("fundamental_score_v5", rows[0])
        self.assertEqual(meta["scored_count"], 0)


class PhilosophySignalV5Tests(unittest.TestCase):
    def _base(self):
        return {
            "simbolo": "AAA",
            "fundamental_score_v5": 80,
            "fundamental_coverage_v5": 90,
            "fx_valid_v5": True,
            "fx_flags_v5": [],
            "strength_score_v3": 82,
            "opportunity_score_v3": 75,
            "confidence_score_v3": 85,
            "risk_score_v3": 30,
            "data_quality_ok_v3": True,
            "caida_pct": -10,
            "history_v3": {
                "momentum_5d_pct": 3,
                "momentum_20d_pct": 8,
                "momentum_60d_pct": 15,
                "momentum_accel": 2,
                "price_volume_confirmation": 100,
            },
        }

    def test_quality_pullback_can_confirm_only_with_stabilization(self):
        row = self._base()
        stage, _ = _v5_signal(row)
        self.assertEqual(stage, "OPORTUNIDAD HÍBRIDA CONFIRMADA")

        row["history_v3"] = dict(row["history_v3"], momentum_5d_pct=-4, momentum_accel=-2, momentum_20d_pct=-5, momentum_60d_pct=-12)
        stage, _ = _v5_signal(row)
        self.assertNotEqual(stage, "OPORTUNIDAD HÍBRIDA CONFIRMADA")

    def test_market_leader_does_not_need_pullback(self):
        row = self._base()
        row["caida_pct"] = 1
        stage, reasons = _v5_signal(row)
        self.assertEqual(stage, "OPORTUNIDAD HÍBRIDA CONFIRMADA")
        self.assertTrue(any("ruta líder" in r for r in reasons))

    def test_no_fundamentals_never_claims_v5_confirmation(self):
        row = self._base()
        row["fundamental_score_v5"] = None
        stage, _ = _v5_signal(row)
        self.assertEqual(stage, "TÉCNICO V3 · SIN FUNDAMENTALES")

    def test_apply_v5_keeps_v3_fields(self):
        row = self._base()
        row["total"] = 77
        with patch.dict(os.environ, {}, clear=True):
            rows, meta = apply_v5([row], {"engine_version": "V3"})
        self.assertEqual(rows[0]["total"], 77)
        self.assertEqual(meta["engine_version"], "V5-HYBRID")


if __name__ == "__main__":
    unittest.main()
