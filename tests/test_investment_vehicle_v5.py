import unittest
from unittest.mock import patch

from services.investment_vehicle_v5 import enrich_investment_vehicles


class InvestmentVehicleV5Tests(unittest.TestCase):
    def test_vehicle_uses_nav_model_not_greenblatt(self):
        rows = [
            {"simbolo":"ICP.B"},
            {"simbolo":"PER"},
        ]
        payload = {
            "ICP.B": {"market_cap":80,"equity":100,"total_assets":120,"net_income":12,"nav_per_share":10,"market_price":8,"distribution_yield_pct":6,"earnings_history":[5,7,9,12],"nav_history":[7,8,9,10]},
            "PER": {"market_cap":110,"equity":100,"total_assets":125,"net_income":8,"nav_per_share":10,"market_price":11,"distribution_yield_pct":3,"earnings_history":[5,6,7,8],"nav_history":[8,8.5,9,10]},
        }
        with patch("services.investment_vehicle_v5.load_fundamentals", return_value=(payload, {"source":"test"})):
            out, meta = enrich_investment_vehicles(rows)
        icp = next(r for r in out if r["simbolo"] == "ICP.B")
        self.assertEqual(icp["industry_type_v5"], "investment_vehicle")
        self.assertIsNotNone(icp["vehicle_score_v5"])
        self.assertEqual(icp["fundamental_score_v5"], icp["vehicle_score_v5"])
        self.assertIsNone(icp["greenblatt_score_v5"])
        self.assertEqual(icp["fundamental_method_v5"], "investment_vehicle_nav_value_quality_usd_bcv")
        self.assertEqual(meta["vehicle_scored_count"], 2)

    def test_missing_vehicle_data_fails_closed(self):
        with patch("services.investment_vehicle_v5.load_fundamentals", return_value=({}, {"source":"test"})):
            out, _ = enrich_investment_vehicles([{"simbolo":"ICP.B"}])
        self.assertIsNone(out[0]["vehicle_score_v5"])
        self.assertEqual(out[0]["vehicle_coverage_v5"], 0.0)


if __name__ == "__main__":
    unittest.main()
