import unittest

from services.fundamental_autoreview_v5 import propose_fail_closed_selections


class FundamentalAutoReviewV5Tests(unittest.TestCase):
    def test_unique_accounting_equation_can_resolve_balance(self):
        review = {
            "valid": True,
            "industry_type": "non_financial",
            "fields": {
                "total_assets": [{"value": 100.0}, {"value": 999.0}],
                "total_liabilities": [{"value": 40.0}, {"value": 500.0}],
                "equity": [{"value": 60.0}, {"value": 200.0}],
                "net_income": [{"value": 10.0}, {"value": 10.0}],
            },
        }
        out = propose_fail_closed_selections(review)
        self.assertTrue(out["valid"])
        self.assertEqual(out["selections"]["total_assets"], 0)
        self.assertEqual(out["selections"]["total_liabilities"], 0)
        self.assertEqual(out["selections"]["equity"], 0)
        self.assertEqual(out["selections"]["net_income"], 0)

    def test_ambiguous_required_field_fails_closed(self):
        review = {
            "valid": True,
            "industry_type": "financial",
            "fields": {
                "total_assets": [{"value": 100.0}],
                "total_liabilities": [{"value": 40.0}],
                "equity": [{"value": 60.0}],
                "net_income": [{"value": 10.0}, {"value": 12.0}],
            },
        }
        out = propose_fail_closed_selections(review)
        self.assertFalse(out["valid"])
        self.assertIn("net_income", out["missing_required"])

    def test_vehicle_does_not_require_net_income(self):
        review = {
            "valid": True,
            "industry_type": "investment_vehicle",
            "fields": {
                "total_assets": [{"value": 100.0}],
                "total_liabilities": [{"value": 25.0}],
                "equity": [{"value": 75.0}],
            },
        }
        out = propose_fail_closed_selections(review)
        self.assertTrue(out["valid"])
        self.assertEqual(out["missing_required"], [])


if __name__ == "__main__":
    unittest.main()
