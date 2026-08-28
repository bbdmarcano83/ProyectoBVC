import unittest

from services.scoring_v3 import enriquecer_resultados_v3, comparar_v2_v3
from services.scoring_engine_v3 import _hist_metrics, _market_regime
from services.scoring_postprocess import apply_sector_and_events
from services.portfolio_v4 import analizar_portafolio_v4, evaluar_rotacion_v4, FEES
from services.backtest_v3 import backtest_symbol, summarize, walk_forward_threshold


class ScoringFoundationTests(unittest.TestCase):
    def _market_snapshot(self):
        return [
            {"simbolo": "AAA", "total": 82, "rend_pct": 120, "liq_score": 25, "liq_vol": 12_000_000,
             "din_avg_ops": 30, "din_change_pct": 85, "din_spread_pct": 2.5, "din_label": "MUY ACTIVO",
             "tend_score": 15, "tend_trend": "up", "caida_pct": -12, "precio": 10,
             "fecha_ultimo": "28-AGO-26", "dias_datos": 120, "señal_compra": False, "sector": "Banca"},
            {"simbolo": "BBB", "total": 55, "rend_pct": 60, "liq_score": 15, "liq_vol": 3_000_000,
             "din_avg_ops": 12, "din_change_pct": 55, "din_spread_pct": 5, "din_label": "ACTIVO",
             "tend_score": 10, "tend_trend": "stable", "caida_pct": -5, "precio": 5,
             "fecha_ultimo": "28-AGO-26", "dias_datos": 80, "señal_compra": False, "sector": "Banca"},
            {"simbolo": "CCC", "total": 25, "rend_pct": 10, "liq_score": 5, "liq_vol": 50_000,
             "din_avg_ops": 1, "din_change_pct": 5, "din_spread_pct": 18, "din_label": "CONGELADO",
             "tend_score": 5, "tend_trend": "down", "caida_pct": -30, "precio": 2,
             "fecha_ultimo": "28-AGO-26", "dias_datos": 15, "señal_compra": True, "sector": "Industria"},
        ]

    def test_foundation_preserva_legacy_y_agrega_capas(self):
        v2 = self._market_snapshot()
        v3, meta = enriquecer_resultados_v3(v2, {"fecha_calculo": "x"})
        aaa = next(r for r in v3 if r["simbolo"] == "AAA")
        self.assertEqual(aaa["legacy_score_v2"], 82.0)
        self.assertIn("confidence_score_v3", aaa)
        self.assertIn("opportunity_score_v3", aaa)
        self.assertEqual(meta["engine_version"], "v3-shadow-foundation")

    def test_quality_gate_bloquea_congelado(self):
        v3, _ = enriquecer_resultados_v3(self._market_snapshot())
        ccc = next(r for r in v3 if r["simbolo"] == "CCC")
        self.assertFalse(ccc["data_quality_ok_v3"])
        self.assertFalse(ccc["señal_compra_v3"])
        self.assertGreaterEqual(ccc["risk_score_v3"], 90)

    def test_shadow_comparator(self):
        v2 = self._market_snapshot()
        v3, _ = enriquecer_resultados_v3(v2)
        diff = comparar_v2_v3(v2, v3)
        self.assertEqual(diff["symbols_compared"], 3)
        self.assertGreaterEqual(diff["changed_buy_signals"], 1)

    def test_sector_postprocess(self):
        rows = self._market_snapshot()
        for r in rows:
            r["score_v3"] = r["total"]
        out, meta = apply_sector_and_events(rows, {})
        self.assertEqual(len(out), 3)
        self.assertIn("Banca", meta["sector_scores_v3"])
        self.assertGreater(meta["sector_scores_v3"]["Banca"], meta["sector_scores_v3"]["Industria"])


class HistoricalMetricsTests(unittest.TestCase):
    def _history(self, n=150):
        rows = []
        for i in range(n):
            price = 100.0 - i * 0.25
            rows.append({
                "FEC": f"D{i}",
                "PRECIO_CIE": price,
                "PRECIO_APERT": price - 0.1,
                "PRECIO_MAX": price + 0.5,
                "PRECIO_MIN": price - 0.5,
                "TOT_OP_NEGOC": 20 if i % 5 else 10,
                "TOT_MONTO_NEGOC": 1_000_000 + (n - i) * 10_000,
            })
        return rows

    def test_hist_metrics_multi_horizon(self):
        m = _hist_metrics(self._history())
        self.assertIsNotNone(m["momentum_5d_pct"])
        self.assertIsNotNone(m["momentum_20d_pct"])
        self.assertIsNotNone(m["momentum_60d_pct"])
        self.assertGreater(m["trading_frequency_60d_pct"], 90)
        self.assertIn("max_drawdown_60d_pct", m)
        self.assertIn("downside_volatility_pct", m)

    def test_market_regime(self):
        rows = [
            {"strength_score_v3": 80, "confidence_score_v3": 80, "din_label": "ACTIVO", "history_v3": {"momentum_20d_pct": 5}},
            {"strength_score_v3": 75, "confidence_score_v3": 75, "din_label": "ACTIVO", "history_v3": {"momentum_20d_pct": 2}},
            {"strength_score_v3": 65, "confidence_score_v3": 70, "din_label": "ACTIVO", "history_v3": {"momentum_20d_pct": 1}},
        ]
        market = _market_regime(rows)
        self.assertIn(market["regime"], {"RISK-ON", "NEUTRAL", "DEFENSIVO", "ESTRES"})
        self.assertGreater(market["breadth_score"], 0)


class PortfolioV4Tests(unittest.TestCase):
    def test_concentracion_salud_y_toma_ganancia(self):
        filas = [
            {"simb": "AAA", "peso_pct": 60, "rend_pct": 55},
            {"simb": "BBB", "peso_pct": 40, "rend_pct": -5},
        ]
        scoring = {
            "AAA": {"score_v3": 82, "confidence_score_v3": 85, "risk_score_v3": 30, "signal_stage_v3": "OBSERVAR"},
            "BBB": {"score_v3": 45, "confidence_score_v3": 60, "risk_score_v3": 75, "signal_stage_v3": "OBSERVAR"},
        }
        out = analizar_portafolio_v4(filas, scoring)
        self.assertEqual(out["riesgo_concentracion"], "alto")
        self.assertEqual(out["ganadores"], 1)
        self.assertEqual(out["perdedores"], 1)
        self.assertIsNotNone(out["score_ponderado"])
        self.assertGreater(out["capital_score_debil_pct"], 0)
        self.assertEqual(out["candidatos_toma_ganancia"][0]["simbolo"], "AAA")

    def test_rotacion_descuenta_friccion(self):
        out = evaluar_rotacion_v4("AAA", 50, "BBB", 80, 12.0)
        self.assertAlmostEqual(out["friccion_rotacion_pct"], FEES.friccion_rotacion_pct())
        self.assertEqual(out["rotacion_economicamente_valida"], out["ventaja_neta_esperada_pct"] > 0)


class BacktestTests(unittest.TestCase):
    def _history(self, n=180):
        rows = []
        for i in range(n):
            price = 200.0 - i * 0.35
            rows.append({
                "FEC": f"D{i}",
                "PRECIO_CIE": price,
                "PRECIO_APERT": price - 0.1,
                "PRECIO_MAX": price + 0.5,
                "PRECIO_MIN": price - 0.5,
                "TOT_OP_NEGOC": 20,
                "TOT_MONTO_NEGOC": 1_500_000,
            })
        return rows

    def test_backtest_is_stateless_and_produces_forward_returns(self):
        recs = backtest_symbol(self._history(), score_threshold=0, step=5)
        self.assertGreater(len(recs), 5)
        summary = summarize(recs)
        self.assertGreater(summary["signals"], 0)
        self.assertGreater(summary["ret_5d"]["n"], 0)

    def test_walk_forward_rejects_small_sample(self):
        self.assertEqual(walk_forward_threshold([])["error"], "muestra_insuficiente")


if __name__ == "__main__":
    unittest.main()
