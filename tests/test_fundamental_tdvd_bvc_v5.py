import unittest

from services.fundamental_source_review_v5 import propose_issuer_specific
from services.fundamental_tdvd_bvc_v5 import _consensus, _extract_current_integer


class FundamentalTdvdBvcV5Tests(unittest.TestCase):
    def test_extracts_grouped_and_compact_current_values(self):
        self.assertEqual(_extract_current_integer(" 227.463.132.627 76.452.090.797"), 227463132627)
        self.assertEqual(_extract_current_integer(" 23.483.735502 23.383.650.959"), 23483735502)
        self.assertEqual(_extract_current_integer(" 331 .044,072 306.369.601"), 331044072)

    def test_rejects_corrupted_four_digit_group(self):
        self.assertIsNone(_extract_current_integer(" 831.044.0072 306.369.601"))

    def test_consensus_requires_two_independent_families(self):
        one = _consensus([
            {"family": "gray2x", "value": 123456789, "page": 3, "line": "x"},
            {"family": "gray2x", "value": 123456789, "page": 3, "line": "x2"},
        ])
        self.assertFalse(one["valid"])
        two = _consensus([
            {"family": "gray2x", "value": 123456789, "page": 3, "line": "x"},
            {"family": "bw2x", "value": 123456789, "page": 3, "line": "x2"},
        ])
        self.assertTrue(two["valid"])
        self.assertEqual(two["value"], 123456789)

    def test_consensus_tie_fails_closed(self):
        result = _consensus([
            {"family": "gray2x", "value": 111111111, "page": 3, "line": "a"},
            {"family": "bw2x", "value": 111111111, "page": 3, "line": "b"},
            {"family": "gray3x", "value": 222222222, "page": 3, "line": "c"},
            {"family": "other", "value": 222222222, "page": 3, "line": "d"},
        ])
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "ocr_consensus_tie")

    @staticmethod
    def _review(*, equity=20.0, preferred=0, income_column=0):
        return {
            "valid": True,
            "symbol": "TDV.D",
            "preferred_column": preferred,
            "fields": {
                "total_assets": [{"index": 0, "value": 100.0, "page": 1, "column_index": 0, "alias": "total activo", "context_quality": "accounting_row"}],
                "total_liabilities": [{"index": 0, "value": 80.0, "page": 2, "column_index": 0, "alias": "total pasivo", "context_quality": "accounting_row"}],
                "equity": [{"index": 0, "value": equity, "page": 1, "column_index": 0, "alias": "total patrimonio", "context_quality": "accounting_row"}],
                "net_income": [{"index": 0, "value": 5.0, "page": 3, "column_index": income_column, "alias": "utilidad (pérdida) neta", "context_quality": "accounting_row"}],
            },
        }

    def test_tdvd_adjacent_pages_exact_equation_is_selected(self):
        result = propose_issuer_specific(self._review())
        self.assertTrue(result["valid"])
        self.assertEqual(result["method"], "tdvd_bvc_adjacent_pages_consensus_ocr")
        self.assertEqual(result["accounting_error_pct"], 0.0)
        self.assertEqual(set(result["selections"]), {"total_assets", "total_liabilities", "equity", "net_income"})

    def test_tdvd_mismatch_or_wrong_column_fails_closed(self):
        self.assertIsNone(propose_issuer_specific(self._review(equity=19.0)))
        self.assertIsNone(propose_issuer_specific(self._review(preferred=1)))
        self.assertIsNone(propose_issuer_specific(self._review(income_column=1)))


if __name__ == "__main__":
    unittest.main()
