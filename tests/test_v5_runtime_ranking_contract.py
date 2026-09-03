import unittest

from services.scoring_runtime_v5 import activate_v5_runtime


class V5RuntimeRankingContractTests(unittest.TestCase):
    def test_v5_ranking_overrides_preexisting_v3_order_without_destroying_v3(self):
        rows = [
            {"simbolo": "V3TOP", "score_v3": 95.0, "total": 95.0, "philosophy_score_v5": 61.0},
            {"simbolo": "V5TOP", "score_v3": 60.0, "total": 60.0, "philosophy_score_v5": 88.0},
        ]

        ranked, metadata = activate_v5_runtime(rows, {"v5": {}})

        self.assertEqual([row["simbolo"] for row in ranked], ["V5TOP", "V3TOP"])
        self.assertEqual(ranked[0]["total"], 88.0)
        self.assertEqual(ranked[0]["score_v3"], 60.0)
        self.assertEqual(ranked[0]["ranking_score_v5"], 88.0)
        self.assertEqual(metadata["active_score_field"], "philosophy_score_v5")
        self.assertEqual(metadata["v5"]["ranking_order"], "philosophy_score_v5_desc")

    def test_missing_v5_score_is_not_coerced_to_zero_and_sorts_last(self):
        rows = [
            {"simbolo": "MISSING", "score_v3": 99.0, "total": 99.0, "philosophy_score_v5": None},
            {"simbolo": "READY", "score_v3": 40.0, "total": 40.0, "philosophy_score_v5": 70.0},
        ]

        ranked, _ = activate_v5_runtime(rows, {})

        self.assertEqual([row["simbolo"] for row in ranked], ["READY", "MISSING"])
        self.assertIsNone(ranked[1]["ranking_score_v5"])
        self.assertEqual(ranked[1]["total"], 99.0)


if __name__ == "__main__":
    unittest.main()
