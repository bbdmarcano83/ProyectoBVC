import unittest
from unittest.mock import patch

from services.fundamental_review_v5 import build_review_package, select_candidates, accept_reviewed_snapshot


class FundamentalReviewV5Tests(unittest.TestCase):
    def _candidates(self):
        return {
            "total_assets": [{"value": 100, "raw": "100", "page": 1, "alias": "total activos", "evidence": "Total activos 100"}],
            "total_liabilities": [{"value": 40, "raw": "40", "page": 1, "alias": "total pasivos", "evidence": "Total pasivos 40"}],
            "equity": [{"value": 60, "raw": "60", "page": 1, "alias": "patrimonio", "evidence": "Patrimonio 60"}],
            "net_income": [
                {"value": 5, "raw": "5", "page": 2, "alias": "resultado neto", "evidence": "2025 Resultado neto 5"},
                {"value": 3, "raw": "3", "page": 2, "alias": "resultado neto", "evidence": "2024 Resultado neto 3"},
            ],
        }

    def test_review_requires_explicit_selection(self):
        review = build_review_package("SVS", self._candidates(), source_url="https://sivensa.com.ve/report.pdf", as_of="2025-09-30")
        self.assertTrue(review["valid"])
        self.assertTrue(review["requires_explicit_selection"])
        self.assertEqual(len(review["fields"]["net_income"]), 2)

    def test_selected_candidate_preserves_evidence(self):
        review = build_review_package("SVS", self._candidates(), source_url="https://sivensa.com.ve/report.pdf", as_of="2025-09-30")
        record, meta = select_candidates(review, {"total_assets": 0, "total_liabilities": 0, "equity": 0, "net_income": 1})
        self.assertTrue(meta["valid"])
        self.assertEqual(record["net_income"], 3)
        self.assertEqual(meta["evidence"]["net_income"]["page"], 2)

    def test_invalid_index_fails_closed(self):
        review = build_review_package("SVS", self._candidates(), source_url="https://sivensa.com.ve/report.pdf", as_of="2025-09-30")
        record, meta = select_candidates(review, {"net_income": 99})
        self.assertFalse(meta["valid"])
        self.assertIn("net_income:indice_fuera_de_rango", meta["errors"])

    def test_declared_statement_scale_is_applied_and_audited(self):
        review = build_review_package("SVS", self._candidates(), source_url="https://sivensa.com.ve/report.pdf", as_of="2025-09-30")
        record, meta = select_candidates(
            review,
            {"total_assets": 0, "equity": 0},
            value_multiplier=1000,
        )
        self.assertTrue(meta["valid"])
        self.assertEqual(record["total_assets"], 100000)
        self.assertEqual(record["equity"], 60000)
        self.assertEqual(meta["evidence"]["total_assets"]["reported_value_multiplier"], 1000)

    def test_invalid_statement_scale_fails_closed(self):
        review = build_review_package("SVS", self._candidates(), source_url="https://sivensa.com.ve/report.pdf", as_of="2025-09-30")
        record, meta = select_candidates(review, {"total_assets": 0}, value_multiplier=0)
        self.assertEqual(record, {})
        self.assertFalse(meta["valid"])
        self.assertEqual(meta["reason"], "invalid_value_multiplier")

    def test_detected_page_scale_mismatch_fails_closed(self):
        candidates = self._candidates()
        candidates["total_assets"][0]["page_value_multiplier"] = 1000
        review = build_review_package("SVS", candidates, source_url="https://sivensa.com.ve/report.pdf", as_of="2025-09-30")
        record, meta = select_candidates(review, {"total_assets": 0}, value_multiplier=1)
        self.assertEqual(record, {})
        self.assertFalse(meta["valid"])
        self.assertIn("total_assets:escala_declarada_no_coincide_con_folio", meta["errors"])

    def test_accept_calls_collector_only_after_explicit_selection(self):
        review = build_review_package("SVS", self._candidates(), source_url="https://sivensa.com.ve/report.pdf", as_of="2025-09-30")
        fake = {"accepted": True, "persisted": True}
        with patch("services.fundamental_review_v5.ingest_normalized_report", return_value=fake) as ingest:
            out = accept_reviewed_snapshot(
                review,
                {"total_assets": 0, "total_liabilities": 0, "equity": 0, "net_income": 0},
                document_type="annual_audited", fiscal_period="FY2025", audited=True,
                currency="VES", monetary_basis="constant_ves_end_period",
                hydrate_fx=False, require_fx=False,
            )
        self.assertTrue(out["accepted"])
        ingest.assert_called_once()
        record = ingest.call_args.args[1]
        self.assertEqual(record["total_assets"], 100)
        self.assertEqual(record["equity"], 60)
        self.assertEqual(record["currency"], "VES")


if __name__ == "__main__":
    unittest.main()
