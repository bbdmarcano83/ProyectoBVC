import unittest

from services.fundamental_source_review_v5 import propose_issuer_specific


class FundamentalSourceReviewV5Tests(unittest.TestCase):
    def test_crecepymes_prefers_earliest_primary_balance(self):
        review = {
            "symbol": "ICP.B",
            "preferred_column": 0,
            "fields": {
                "total_assets": [
                    {"index": 0, "value": 200.0, "page": 4, "column_index": 0},
                    {"index": 1, "value": 50.0, "page": 34, "column_index": 0},
                ],
                "total_liabilities": [
                    {"index": 0, "value": 80.0, "page": 4, "column_index": 0},
                    {"index": 1, "value": 20.0, "page": 34, "column_index": 0},
                ],
                "equity": [
                    {"index": 0, "value": 120.0, "page": 4, "column_index": 0},
                    {"index": 1, "value": 30.0, "page": 34, "column_index": 0},
                ],
            },
        }
        out = propose_issuer_specific(review)
        self.assertIsNotNone(out)
        self.assertTrue(out["valid"])
        self.assertEqual(out["balance_page"], 4)
        self.assertEqual(out["selections"]["total_assets"], 0)
        self.assertEqual(out["selections"]["equity"], 0)

    def test_mercantil_requires_nearby_unique_net_income(self):
        review = {
            "symbol": "MVZ.A",
            "preferred_column": 0,
            "fields": {
                "total_assets": [{"index": 0, "value": 100.0, "page": 5, "column_index": 0}],
                "total_liabilities": [{"index": 0, "value": 40.0, "page": 5, "column_index": 0}],
                "equity": [{"index": 0, "value": 60.0, "page": 5, "column_index": 0}],
                "net_income": [
                    {"index": 0, "value": 12.0, "page": 6, "column_index": 0},
                    {"index": 1, "value": 999.0, "page": 30, "column_index": 0},
                ],
            },
        }
        out = propose_issuer_specific(review)
        self.assertIsNotNone(out)
        self.assertTrue(out["valid"])
        self.assertEqual(out["selections"]["net_income"], 0)

    def test_mercantil_fails_when_income_is_ambiguous_on_same_page(self):
        review = {
            "symbol": "MVZ.A",
            "preferred_column": 0,
            "fields": {
                "total_assets": [{"index": 0, "value": 100.0, "page": 5, "column_index": 0}],
                "total_liabilities": [{"index": 0, "value": 40.0, "page": 5, "column_index": 0}],
                "equity": [{"index": 0, "value": 60.0, "page": 5, "column_index": 0}],
                "net_income": [
                    {"index": 0, "value": 12.0, "page": 6, "column_index": 0},
                    {"index": 1, "value": 13.0, "page": 6, "column_index": 0},
                ],
            },
        }
        self.assertIsNone(propose_issuer_specific(review))


if __name__ == "__main__":
    unittest.main()
