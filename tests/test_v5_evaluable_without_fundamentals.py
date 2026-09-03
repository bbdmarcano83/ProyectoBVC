import unittest

from services.scoring_engine_v5 import _philosophy_score, _v5_signal


class EvaluabilityContractV5Tests(unittest.TestCase):
    def test_valid_asset_without_fundamental_is_scored_from_available_pillars(self):
        row = {
            "simbolo": "NUEVA",
            "fundamental_score_v5": None,
            "fundamental_evidence_confidence_v5": 0,
            "strength_score_v3": 70,
            "opportunity_score_v3": 65,
            "confidence_score_v3": 70,
            "risk_score_v3": 40,
            "data_quality_ok_v3": True,
            "caida_pct": 0,
            "history_v3": {
                "momentum_5d_pct": 1,
                "momentum_20d_pct": 2,
                "momentum_60d_pct": 3,
                "momentum_accel": 1,
                "price_volume_confirmation": 65,
            },
        }
        score, coverage = _philosophy_score(row)
        stage, _ = _v5_signal(row)
        self.assertIsNotNone(score)
        self.assertGreater(score, 0)
        self.assertGreater(coverage, 0)
        self.assertNotIn("BLOQUE", stage.upper())


if __name__ == "__main__":
    unittest.main()
