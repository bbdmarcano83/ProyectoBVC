import unittest

from services.fundamental_source_review_v5 import propose_issuer_specific


class FundamentalSourceReviewV5Tests(unittest.TestCase):
    def test_bnc_uses_only_consolidated_exact_rows_across_folios(self):
        scope = "bnc_consolidated_foreign_branches"
        review = {
            "symbol": "BNC", "preferred_column": 0,
            "fields": {
                "total_assets": [
                    {"index": 0, "alias": "total del activo", "evidence": "TOTAL DEL ACTIVO 80", "value": 80, "page": 5, "column_index": 0, "page_scope": "bnc_venezuela_operations"},
                    {"index": 1, "alias": "total del activo", "evidence": "TOTAL DEL ACTIVO 100", "value": 100, "page": 8, "column_index": 0, "page_scope": None},
                ],
                "total_liabilities": [
                    {"index": 2, "alias": "total del pasivo", "evidence": "TOTAL DEL PASIVO 50", "value": 50, "page": 6, "column_index": 0, "page_scope": "bnc_venezuela_operations"},
                    {"index": 3, "alias": "total del pasivo", "evidence": "TOTAL DEL PASIVO 60", "value": 60, "page": 9, "column_index": 0, "page_scope": scope},
                ],
                "equity": [
                    {"index": 4, "alias": "total del patrimonio", "evidence": "TOTAL DEL PATRIMONIO 30", "value": 30, "page": 6, "column_index": 0, "page_scope": "bnc_venezuela_operations"},
                    {"index": 5, "alias": "total del patrimonio", "evidence": "TOTAL DEL PATRIMONIO 40", "value": 40, "page": 9, "column_index": 0, "page_scope": scope},
                ],
                "net_income": [
                    {"index": 6, "alias": "resultado neto", "evidence": "RESULTADO NETO 7", "value": 7, "page": 10, "column_index": 0, "page_scope": scope},
                ],
            },
        }
        out = propose_issuer_specific(review)
        self.assertEqual(out["selections"], {
            "total_assets": 1, "total_liabilities": 3, "equity": 5, "net_income": 6,
        })
        self.assertEqual(out["method"], "bnc_consolidated_exact_labels_layout_current_column")

    def test_bnc_fails_closed_without_consolidated_scope(self):
        review = {
            "symbol": "BNC", "preferred_column": 0,
            "fields": {
                "total_assets": [{"alias": "total del activo", "evidence": "TOTAL DEL ACTIVO 80", "value": 80, "page": 5, "column_index": 0, "page_scope": "bnc_venezuela_operations"}],
                "total_liabilities": [{"alias": "total del pasivo", "evidence": "TOTAL DEL PASIVO 50", "value": 50, "page": 6, "column_index": 0, "page_scope": "bnc_venezuela_operations"}],
                "equity": [{"alias": "total del patrimonio", "evidence": "TOTAL DEL PATRIMONIO 30", "value": 30, "page": 6, "column_index": 0, "page_scope": "bnc_venezuela_operations"}],
                "net_income": [{"alias": "resultado neto", "evidence": "RESULTADO NETO 7", "value": 7, "page": 7, "column_index": 0, "page_scope": "bnc_venezuela_operations"}],
            },
        }
        self.assertIsNone(propose_issuer_specific(review))

    def test_cantv_uses_exact_labels_across_split_balance_pages(self):
        review = {
            "symbol": "TDV.D",
            "preferred_column": 0,
            "fields": {
                "total_assets": [
                    {"index": 0, "alias": "total activo", "evidence": "Total activo corriente 10", "value": 10, "page": 1, "column_index": 0},
                    {"index": 1, "alias": "total activo", "evidence": "Total Activo 100", "value": 100, "page": 1, "column_index": 0},
                ],
                "total_liabilities": [
                    {"index": 2, "alias": "total pasivo", "evidence": "Total pasivo 60", "value": 60, "page": 2, "column_index": 0},
                ],
                "equity": [
                    {"index": 6, "alias": "total patrimonio", "evidence": "_ Total patrimonio 40.000 39.000", "value": 40000, "page": 1, "column_index": 0},
                    {"index": 3, "alias": "total patrimonio", "evidence": "Total patrimonio 40", "value": 40, "page": 1, "column_index": 0},
                    {"index": 4, "alias": "total patrimonio", "evidence": "Total patrimonio y pasivo 100", "value": 100, "page": 2, "column_index": 0},
                ],
                "net_income": [
                    {"index": 5, "alias": "utilidad (pérdida) neta", "evidence": "Utilidad (Pérdida) neta 7", "value": 7, "page": 3, "column_index": 0},
                ],
            },
        }
        out = propose_issuer_specific(review)
        self.assertTrue(out["valid"])
        self.assertEqual(out["selections"], {
            "total_assets": 1, "total_liabilities": 2, "equity": 3, "net_income": 5,
        })
        self.assertEqual(out["accounting_error_pct"], 0.0)

    def test_cantv_fails_closed_when_two_exact_triplets_reconcile(self):
        review = {
            "symbol": "TDV.D", "preferred_column": 0,
            "fields": {
                "total_assets": [
                    {"index": 0, "alias": "total activo", "evidence": "Total activo 100", "value": 100, "page": 1, "column_index": 0},
                    {"index": 1, "alias": "total activo", "evidence": "Total activo 200", "value": 200, "page": 1, "column_index": 0},
                ],
                "total_liabilities": [
                    {"index": 2, "alias": "total pasivo", "evidence": "Total pasivo 60", "value": 60, "page": 2, "column_index": 0},
                    {"index": 3, "alias": "total pasivo", "evidence": "Total pasivo 160", "value": 160, "page": 2, "column_index": 0},
                ],
                "equity": [{"index": 4, "alias": "total patrimonio", "evidence": "Total patrimonio 40", "value": 40, "page": 1, "column_index": 0}],
                "net_income": [{"index": 5, "alias": "utilidad (pérdida) neta", "evidence": "Utilidad (Pérdida) neta 7", "value": 7, "page": 3, "column_index": 0}],
            },
        }
        self.assertIsNone(propose_issuer_specific(review))

    def test_cantv_fails_closed_when_split_balance_does_not_reconcile(self):
        review = {
            "symbol": "TDV.D", "preferred_column": 0,
            "fields": {
                "total_assets": [{"alias": "total activo", "evidence": "Total activo 100", "value": 100, "page": 1, "column_index": 0}],
                "total_liabilities": [{"alias": "total pasivo", "evidence": "Total pasivo 61", "value": 61, "page": 2, "column_index": 0}],
                "equity": [{"alias": "total patrimonio", "evidence": "Total patrimonio 40", "value": 40, "page": 1, "column_index": 0}],
                "net_income": [{"alias": "utilidad (pérdida) neta", "evidence": "Utilidad (Pérdida) neta 7", "value": 7, "page": 3, "column_index": 0}],
            },
        }
        self.assertIsNone(propose_issuer_specific(review))

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
