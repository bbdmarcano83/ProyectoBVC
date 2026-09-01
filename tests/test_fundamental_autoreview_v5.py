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

    def test_comparative_current_period_uses_column_zero(self):
        review = {
            "valid": True,
            "industry_type": "non_financial",
            "preferred_column": 0,
            "fields": {
                "total_assets": [
                    {"index": 0, "value": 120.0, "page": 4, "column_index": 0},
                    {"index": 1, "value": 100.0, "page": 4, "column_index": 1},
                ],
                "total_liabilities": [
                    {"index": 0, "value": 50.0, "page": 4, "column_index": 0},
                    {"index": 1, "value": 40.0, "page": 4, "column_index": 1},
                ],
                "equity": [
                    {"index": 0, "value": 70.0, "page": 4, "column_index": 0},
                    {"index": 1, "value": 60.0, "page": 4, "column_index": 1},
                ],
                "net_income": [
                    {"index": 0, "value": 12.0, "page": 5, "column_index": 0},
                    {"index": 1, "value": 10.0, "page": 5, "column_index": 1},
                ],
            },
        }
        out = propose_fail_closed_selections(review)
        self.assertTrue(out["valid"])
        self.assertEqual(out["selections"]["total_assets"], 0)
        self.assertEqual(out["selections"]["net_income"], 0)

    def test_comparative_prior_period_uses_column_one(self):
        review = {
            "valid": True,
            "industry_type": "non_financial",
            "preferred_column": 1,
            "fields": {
                "total_assets": [
                    {"index": 0, "value": 120.0, "page": 4, "column_index": 0},
                    {"index": 1, "value": 100.0, "page": 4, "column_index": 1},
                ],
                "total_liabilities": [
                    {"index": 0, "value": 50.0, "page": 4, "column_index": 0},
                    {"index": 1, "value": 40.0, "page": 4, "column_index": 1},
                ],
                "equity": [
                    {"index": 0, "value": 70.0, "page": 4, "column_index": 0},
                    {"index": 1, "value": 60.0, "page": 4, "column_index": 1},
                ],
                "net_income": [
                    {"index": 0, "value": 12.0, "page": 5, "column_index": 0},
                    {"index": 1, "value": 10.0, "page": 5, "column_index": 1},
                ],
            },
        }
        out = propose_fail_closed_selections(review)
        self.assertTrue(out["valid"])
        self.assertEqual(out["selections"]["total_assets"], 1)
        self.assertEqual(out["selections"]["total_liabilities"], 1)
        self.assertEqual(out["selections"]["equity"], 1)
        self.assertEqual(out["selections"]["net_income"], 1)


if __name__ == "__main__":
    unittest.main()
