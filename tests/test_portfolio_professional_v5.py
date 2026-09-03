import unittest
from pathlib import Path

from services.portfolio_professional_v5 import build_professional_open_metrics


class PortfolioProfessionalV5Tests(unittest.TestCase):
    def test_usd_pnl_uses_historical_entry_fx_not_current_fx_for_cost(self):
        positions = [{"simb": "AAA", "cantidad": 10, "costo_total": 1000, "val_mkt": 1800}]
        txs = [{
            "simbolo": "AAA", "tipo": "compra", "cantidad": 10,
            "precio": 100, "neto": 1000, "fecha": "2026-01-02", "tasa_bcv": 100,
        }]
        out = build_professional_open_metrics(positions, txs, current_fx=200)

        self.assertEqual(out["cost_usd_historical"], 10.0)
        self.assertEqual(out["market_value_usd"], 9.0)
        self.assertEqual(out["pnl_usd"], -1.0)
        self.assertEqual(out["return_usd_pct"], -10.0)
        self.assertEqual(out["return_bs_pct"], 80.0)
        self.assertEqual(out["fx_change_pct"], 100.0)
        self.assertEqual(out["fx_effect_pp"], -90.0)
        row = out["positions"][0]
        self.assertEqual(row["cost_usd_historical"], 10.0)
        self.assertEqual(row["current_value_usd"], 9.0)
        self.assertEqual(row["pnl_usd"], -1.0)

    def test_missing_historical_fx_fails_closed_for_usd_but_preserves_bs(self):
        positions = [{"simb": "AAA", "cantidad": 10, "costo_total": 1000, "val_mkt": 1500}]
        txs = [{
            "simbolo": "AAA", "tipo": "compra", "cantidad": 10,
            "precio": 100, "neto": 1000, "fecha": "2026-01-02",
        }]
        out = build_professional_open_metrics(positions, txs, current_fx=200)

        self.assertEqual(out["pnl_bs"], 500.0)
        self.assertEqual(out["return_bs_pct"], 50.0)
        self.assertIsNone(out["pnl_usd"])
        self.assertIsNone(out["return_usd_pct"])
        self.assertEqual(out["usd_coverage_pct"], 0.0)
        self.assertFalse(out["positions"][0]["usd_comparable"])

    def test_partial_fx_coverage_is_not_silently_imputed(self):
        positions = [{"simb": "AAA", "cantidad": 10, "costo_total": 1000, "val_mkt": 1500}]
        txs = [
            {"simbolo": "AAA", "tipo": "compra", "cantidad": 5, "neto": 500, "fecha": "2026-01-02", "tasa_bcv": 100},
            {"simbolo": "AAA", "tipo": "compra", "cantidad": 5, "neto": 500, "fecha": "2026-02-02"},
        ]
        out = build_professional_open_metrics(positions, txs, current_fx=200)

        self.assertEqual(out["usd_coverage_pct"], 50.0)
        row = out["positions"][0]
        self.assertEqual(row["usd_coverage_pct"], 50.0)
        self.assertEqual(row["cost_usd_historical"], 5.0)
        self.assertEqual(row["current_value_usd"], 3.75)
        self.assertEqual(row["return_usd_pct"], -25.0)

    def test_position_creation_fallback_can_use_explicit_historical_fx(self):
        positions = [{
            "simb": "AAA", "cantidad": 10, "costo_total": 1000, "val_mkt": 1200,
            "creado_en": "2026-01-02", "fx_inicio": 100,
        }]
        out = build_professional_open_metrics(positions, [], current_fx=200)

        row = out["positions"][0]
        self.assertEqual(row["source"], "position_created_fallback")
        self.assertTrue(row["usd_comparable"])
        self.assertEqual(row["cost_usd_historical"], 10.0)
        self.assertEqual(row["current_value_usd"], 6.0)
        self.assertEqual(row["return_usd_pct"], -40.0)

    def test_fees_use_transaction_date_fx_when_available(self):
        positions = [{"simb": "AAA", "cantidad": 10, "costo_total": 1000, "val_mkt": 1000}]
        txs = [{
            "simbolo": "AAA", "tipo": "compra", "cantidad": 10, "neto": 1000,
            "fecha": "2026-01-02", "tasa_bcv": 100, "fee_total": 20,
        }]
        out = build_professional_open_metrics(positions, txs, current_fx=200)
        self.assertEqual(out["fees_total_bs"], 20.0)
        self.assertEqual(out["fees_total_usd_historical"], 0.2)
        self.assertEqual(out["fees_usd_coverage_pct"], 100.0)

    def test_template_exposes_professional_usd_columns_and_fail_closed_copy(self):
        text = Path("templates/portafolio.html").read_text(encoding="utf-8")
        for marker in (
            "Lectura profesional USD · V5",
            "Costo USD hist.",
            "P/L USD",
            "Ret USD",
            "Efecto FX",
            "Contrib. P/L USD",
            'data-prof="coverage-usd"',
            "nunca se aproxima con la tasa actual",
        ):
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
