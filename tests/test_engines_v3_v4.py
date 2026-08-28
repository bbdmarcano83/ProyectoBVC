import unittest

from services.scoring_v3 import enriquecer_resultado
from services.portfolio_v4 import analizar_portafolio_v4


class ScoringV3Tests(unittest.TestCase):
    def test_preserva_campos_legacy_y_agrega_v3(self):
        row = {
            "simbolo": "TEST",
            "total": 80,
            "liq_score": 20,
            "liq_vol": 1000000,
            "caida_pct": -16,
            "precio": 10,
            "fecha_ultimo": "28-AGO-26",
            "dias_datos": 30,
        }
        out = enriquecer_resultado(row)
        self.assertEqual(out["simbolo"], "TEST")
        self.assertEqual(out["score_v3"], 80.0)
        self.assertEqual(out["score_class_v3"], "alto")
        self.assertTrue(out["data_quality_ok_v3"])
        self.assertTrue(out["señal_compra_v3"])

    def test_quality_gate_bloquea_senal(self):
        row = {"total": 90, "liq_score": 25, "caida_pct": -25, "precio": 0}
        out = enriquecer_resultado(row)
        self.assertFalse(out["data_quality_ok_v3"])
        self.assertFalse(out["señal_compra_v3"])


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
