import unittest

from services.scoring_v3 import enriquecer_resultados_v3, comparar_v2_v3
from services.portfolio_v4 import analizar_portafolio_v4


class ScoringV3Tests(unittest.TestCase):
    def _market_snapshot(self):
        return [
            {
                "simbolo": "AAA",
                "total": 82,
                "rend_pct": 120,
                "liq_score": 25,
                "liq_vol": 12_000_000,
                "din_avg_ops": 30,
                "din_change_pct": 85,
                "din_spread_pct": 2.5,
                "din_label": "MUY ACTIVO",
                "tend_score": 15,
                "tend_trend": "up",
                "caida_pct": -12,
                "precio": 10,
                "fecha_ultimo": "28-AGO-26",
                "dias_datos": 120,
                "señal_compra": False,
            },
            {
                "simbolo": "BBB",
                "total": 55,
                "rend_pct": 60,
                "liq_score": 15,
                "liq_vol": 3_000_000,
                "din_avg_ops": 12,
                "din_change_pct": 55,
                "din_spread_pct": 5,
                "din_label": "ACTIVO",
                "tend_score": 10,
                "tend_trend": "stable",
                "caida_pct": -5,
                "precio": 5,
                "fecha_ultimo": "28-AGO-26",
                "dias_datos": 80,
                "señal_compra": False,
            },
            {
                "simbolo": "CCC",
                "total": 25,
                "rend_pct": 10,
                "liq_score": 5,
                "liq_vol": 50_000,
                "din_avg_ops": 1,
                "din_change_pct": 5,
                "din_spread_pct": 18,
                "din_label": "CONGELADO",
                "tend_score": 5,
                "tend_trend": "down",
                "caida_pct": -30,
                "precio": 2,
                "fecha_ultimo": "28-AGO-26",
                "dias_datos": 15,
                "señal_compra": True,
            },
        ]

    def test_v3_agrega_capas_y_preserva_legacy(self):
        v2 = self._market_snapshot()
        v3, meta = enriquecer_resultados_v3(v2, {"fecha_calculo": "x"})
        aaa = next(r for r in v3 if r["simbolo"] == "AAA")
        self.assertEqual(aaa["legacy_score_v2"], 82.0)
        self.assertIn("confidence_score_v3", aaa)
        self.assertIn("strength_score_v3", aaa)
        self.assertIn("opportunity_score_v3", aaa)
        self.assertIn("risk_score_v3", aaa)
        self.assertTrue(aaa["data_quality_ok_v3"])
        self.assertEqual(meta["engine_version"], "v3-shadow-foundation")

    def test_quality_gate_bloquea_activo_congelado(self):
        v3, _ = enriquecer_resultados_v3(self._market_snapshot())
        ccc = next(r for r in v3 if r["simbolo"] == "CCC")
        self.assertFalse(ccc["data_quality_ok_v3"])
        self.assertFalse(ccc["señal_compra_v3"])
        self.assertGreaterEqual(ccc["risk_score_v3"], 90)

    def test_comparador_shadow_reporta_cambios(self):
        v2 = self._market_snapshot()
        v3, _ = enriquecer_resultados_v3(v2)
        diff = comparar_v2_v3(v2, v3)
        self.assertEqual(diff["symbols_compared"], 3)
        self.assertGreaterEqual(diff["changed_buy_signals"], 1)


class PortfolioV4Tests(unittest.TestCase):
    def test_detecta_concentracion_y_toma_ganancia(self):
        filas = [
            {"simb": "AAA", "peso_pct": 60, "rend_pct": 55},
            {"simb": "BBB", "peso_pct": 40, "rend_pct": -5},
        ]
        out = analizar_portafolio_v4(filas)
        self.assertEqual(out["riesgo_concentracion"], "alto")
        self.assertEqual(out["ganadores"], 1)
        self.assertEqual(out["perdedores"], 1)
        self.assertEqual(out["candidatos_toma_ganancia"][0]["simbolo"], "AAA")


if __name__ == "__main__":
    unittest.main()
