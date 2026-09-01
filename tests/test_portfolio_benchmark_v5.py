import unittest

from services.portfolio_benchmark_v5 import (
    compare_open_portfolio_to_ibc,
    normalize_ibc_points,
    ibc_asof,
    reconstruct_open_lots,
)


class PortfolioBenchmarkV5Tests(unittest.TestCase):
    def test_ibc_asof_forward_fills_weekend(self):
        pts = normalize_ibc_points([
            {"date": "2026-01-02", "close": 1000},
            {"date": "2026-01-05", "close": 1050},
        ])
        self.assertEqual(ibc_asof(pts, __import__('datetime').date(2026, 1, 4)), 1000)

    def test_fifo_lots_remove_sold_quantity(self):
        txs = [
            {"simbolo":"AAA","tipo":"compra","cantidad":10,"precio":10,"neto":100,"fecha":"2026-01-02","tasa_bcv":100},
            {"simbolo":"AAA","tipo":"compra","cantidad":10,"precio":20,"neto":200,"fecha":"2026-02-02","tasa_bcv":200},
            {"simbolo":"AAA","tipo":"venta","cantidad":5,"precio":30,"fecha":"2026-03-02"},
        ]
        lots = reconstruct_open_lots(txs, "AAA")
        self.assertEqual(len(lots), 2)
        self.assertAlmostEqual(sum(x.qty for x in lots), 15)
        self.assertAlmostEqual(lots[0].cost_bs, 50)
        self.assertAlmostEqual(lots[1].cost_bs, 200)

    def test_portfolio_can_beat_ibc_in_bs_and_usd(self):
        positions = [
            {"simb":"AAA","cantidad":10,"costo_total":1000,"val_mkt":1800,"creado_en":"2026-01-02"},
        ]
        txs = [
            {"simbolo":"AAA","tipo":"compra","cantidad":10,"precio":100,"neto":1000,"fecha":"2026-01-02","tasa_bcv":100},
        ]
        ibc = [
            {"date":"2026-01-02","close":1000},
            {"date":"2026-09-01","close":1500},
        ]
        out = compare_open_portfolio_to_ibc(positions, txs, ibc, current_ibc=1500, current_fx=200)
        self.assertTrue(out["available"])
        self.assertAlmostEqual(out["portfolio_return_bs_pct"], 80.0)
        self.assertAlmostEqual(out["ibc_return_bs_pct"], 50.0)
        self.assertAlmostEqual(out["alpha_bs_pp"], 30.0)
        self.assertEqual(out["coverage_pct"], 100.0)
        # Inicial: 1000/100 = $10. Actual cartera: 1800/200 = $9 => -10%.
        self.assertAlmostEqual(out["portfolio_return_usd_pct"], -10.0)
        # IBC sintético: 1000 * 1.5 = 1500 Bs / 200 = $7.5 => -25%.
        self.assertAlmostEqual(out["ibc_return_usd_pct"], -25.0)
        self.assertAlmostEqual(out["alpha_usd_pp"], 15.0)
        self.assertTrue(out["beats_ibc_usd"])
        self.assertEqual(out["usd_coverage_pct"], 100.0)

    def test_missing_historical_fx_keeps_bs_benchmark_but_hides_usd(self):
        positions = [{"simb":"AAA","cantidad":10,"costo_total":1000,"val_mkt":1500,"creado_en":"2026-01-02"}]
        txs = [{"simbolo":"AAA","tipo":"compra","cantidad":10,"precio":100,"neto":1000,"fecha":"2026-01-02"}]
        ibc = [{"date":"2026-01-02","close":1000},{"date":"2026-09-01","close":1200}]
        out = compare_open_portfolio_to_ibc(positions, txs, ibc, current_fx=200)
        self.assertTrue(out["available"])
        self.assertIsNone(out["portfolio_return_usd_pct"])
        self.assertEqual(out["usd_coverage_pct"], 0.0)

    def test_unreconciled_position_fails_closed_without_date_fallback(self):
        positions = [{"simb":"AAA","cantidad":20,"costo_total":1000,"val_mkt":1200}]
        txs = [{"simbolo":"AAA","tipo":"compra","cantidad":10,"precio":100,"neto":1000,"fecha":"2026-01-02","tasa_bcv":100}]
        ibc = [{"date":"2026-01-02","close":1000},{"date":"2026-09-01","close":1100}]
        out = compare_open_portfolio_to_ibc(positions, txs, ibc, current_fx=200)
        self.assertFalse(out["available"])
        self.assertEqual(out["reason"], "cobertura_insuficiente")
        self.assertEqual(out["coverage_pct"], 0.0)

    def test_unreconciled_position_does_not_distort_covered_alpha(self):
        positions = [
            {"simb":"AAA","cantidad":10,"costo_total":1000,"val_mkt":1500},
            {"simb":"BBB","cantidad":20,"costo_total":1000,"val_mkt":10000},
        ]
        txs = [
            {"simbolo":"AAA","tipo":"compra","cantidad":10,"precio":100,"neto":1000,"fecha":"2026-01-02","tasa_bcv":100},
            # BBB no reconcilia y no tiene fecha fallback.
            {"simbolo":"BBB","tipo":"compra","cantidad":10,"precio":100,"neto":1000,"fecha":"2026-01-02","tasa_bcv":100},
        ]
        ibc = [{"date":"2026-01-02","close":1000},{"date":"2026-09-01","close":1200}]
        out = compare_open_portfolio_to_ibc(positions, txs, ibc, current_fx=200)

        self.assertTrue(out["available"])
        self.assertAlmostEqual(out["portfolio_return_bs_pct"], 50.0)
        self.assertAlmostEqual(out["ibc_return_bs_pct"], 20.0)
        self.assertAlmostEqual(out["alpha_bs_pp"], 30.0)
        self.assertEqual(out["eligible_cost_bs"], 2000.0)
        self.assertEqual(out["covered_cost_bs"], 1000.0)
        self.assertEqual(out["coverage_pct"], 50.0)

    def test_partial_fx_coverage_is_calculated_per_lot(self):
        positions = [{"simb":"AAA","cantidad":10,"costo_total":1000,"val_mkt":1500}]
        txs = [
            {"simbolo":"AAA","tipo":"compra","cantidad":5,"precio":100,"neto":500,"fecha":"2026-01-02","tasa_bcv":100},
            {"simbolo":"AAA","tipo":"compra","cantidad":5,"precio":100,"neto":500,"fecha":"2026-02-02"},
        ]
        ibc = [
            {"date":"2026-01-02","close":1000},
            {"date":"2026-02-02","close":1100},
            {"date":"2026-09-01","close":1200},
        ]
        out = compare_open_portfolio_to_ibc(positions, txs, ibc, current_fx=200)

        self.assertTrue(out["available"])
        self.assertEqual(out["coverage_pct"], 100.0)
        self.assertEqual(out["usd_coverage_pct"], 50.0)
        # Sólo el primer lote entra en USD: 500/100=$5; valor actual asignado
        # por cantidad = 750 Bs / 200 = $3.75 => -25%.
        self.assertAlmostEqual(out["portfolio_return_usd_pct"], -25.0)
        # IBC primer lote: 500 * 1200/1000 = 600 Bs / 200 = $3 => -40%.
        self.assertAlmostEqual(out["ibc_return_usd_pct"], -40.0)
        self.assertAlmostEqual(out["alpha_usd_pp"], 15.0)

    def test_lot_before_ibc_history_is_excluded_from_returns_and_coverage(self):
        positions = [{"simb":"AAA","cantidad":10,"costo_total":1000,"val_mkt":1500}]
        txs = [
            {"simbolo":"AAA","tipo":"compra","cantidad":5,"precio":100,"neto":500,"fecha":"2025-12-01","tasa_bcv":80},
            {"simbolo":"AAA","tipo":"compra","cantidad":5,"precio":100,"neto":500,"fecha":"2026-01-02","tasa_bcv":100},
        ]
        ibc = [
            {"date":"2026-01-02","close":1000},
            {"date":"2026-09-01","close":1200},
        ]
        out = compare_open_portfolio_to_ibc(positions, txs, ibc, current_fx=200)

        self.assertTrue(out["available"])
        self.assertEqual(out["coverage_pct"], 50.0)
        self.assertEqual(out["covered_cost_bs"], 500.0)
        # Sólo la mitad cubierta usa también la mitad del valor actual: 750/500.
        self.assertAlmostEqual(out["portfolio_return_bs_pct"], 50.0)
        self.assertAlmostEqual(out["ibc_return_bs_pct"], 20.0)


if __name__ == "__main__":
    unittest.main()
