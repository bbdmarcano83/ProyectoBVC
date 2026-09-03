import unittest

from services.alertas_cierre import _score, _stage, generar_alerta_pro


class V5AlertParityTests(unittest.IsolatedAsyncioTestCase):
    def test_active_alert_score_prefers_v5_over_v3(self):
        row = {
            "score_v3": 92.0,
            "total": 71.0,
            "philosophy_score_v5": 71.0,
        }
        self.assertEqual(_score(row), 71.0)

    def test_active_stage_prefers_v5(self):
        row = {
            "signal_stage_v3": "OPORTUNIDAD CONFIRMADA",
            "signal_stage_v5": "OBSERVAR · SIN FUNDAMENTAL",
        }
        self.assertEqual(_stage(row), "OBSERVAR · SIN FUNDAMENTAL")

    async def test_v3_buy_flag_does_not_create_confirmed_v5_alert(self):
        rows = [{
            "simbolo": "TEST",
            "score_v3": 95.0,
            "total": 66.0,
            "philosophy_score_v5": 66.0,
            "signal_stage_v3": "OPORTUNIDAD CONFIRMADA",
            "signal_stage_v5": "OBSERVAR · SIN FUNDAMENTAL",
            "señal_compra_v3": True,
            "confidence_score_v3": 70,
            "risk_score_v3": 30,
        }]
        message = await generar_alerta_pro(rows, 0, {"v5": {"active_score_field": "philosophy_score_v5"}})
        self.assertNotIn("🟢 OPORTUNIDADES CONFIRMADAS", message)

    async def test_market_opportunity_without_fundamental_is_separate_from_confirmed(self):
        rows = [{
            "simbolo": "TEST",
            "score_v3": 55.0,
            "total": 78.0,
            "philosophy_score_v5": 78.0,
            "signal_stage_v5": "OPORTUNIDAD DE MERCADO · SIN FUNDAMENTAL",
            "confidence_score_v3": 72,
            "risk_score_v3": 35,
        }]
        message = await generar_alerta_pro(rows, 0, {"v5": {}})
        self.assertIn("OPORTUNIDADES DE MERCADO · SIN FUNDAMENTAL", message)
        self.assertIn("Score 78.0", message)
        self.assertNotIn("🟢 OPORTUNIDADES CONFIRMADAS", message)


if __name__ == "__main__":
    unittest.main()
