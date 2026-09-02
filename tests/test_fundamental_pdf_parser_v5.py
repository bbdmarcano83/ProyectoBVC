import hashlib
import unittest

from services.fundamental_pdf_parser_v5 import extract_candidates_from_pages, source_document_sha256


class FundamentalPdfParserV5Tests(unittest.TestCase):
    def test_extracts_candidates_with_page_evidence(self):
        pages = [
            "Balance general Total activos Bs 1.234.567,89 Total pasivos Bs 700.000,00 Patrimonio Bs 534.567,89",
            "Estado de resultados Resultado neto Bs 85.400,50 Ingresos totales Bs 900.000,00",
        ]
        out = extract_candidates_from_pages(pages)
        self.assertIn("total_assets", out)
        self.assertIn("total_liabilities", out)
        self.assertIn("equity", out)
        self.assertIn("net_income", out)
        self.assertEqual(out["total_assets"][0]["page"], 1)
        self.assertAlmostEqual(out["total_assets"][0]["value"], 1234567.89)
        self.assertAlmostEqual(out["net_income"][0]["value"], 85400.50)
        self.assertTrue(out["equity"][0]["evidence"])

    def test_comparative_columns_are_not_concatenated(self):
        out = extract_candidates_from_pages([
            "Total pasivo corriente 348.224.455 466.175.472\n"
            "Total patrimonio de los accionistas 4.100.000.000 3.900.000.000"
        ])
        liabilities = out["total_liabilities"]
        self.assertEqual(liabilities[0]["value"], 348224455.0)
        self.assertEqual(liabilities[1]["value"], 466175472.0)
        self.assertEqual(liabilities[0]["column_index"], 0)
        self.assertEqual(liabilities[1]["column_index"], 1)
        self.assertEqual(liabilities[0]["context_quality"], "accounting_row")
        self.assertLess(liabilities[0]["value"], 1e12)

    def test_ocr_space_after_thousands_dot_is_repaired(self):
        out = extract_candidates_from_pages(["Resultado neto (404. 499.712) (346.028.278)"])
        self.assertEqual(out["net_income"][0]["value"], -404499712.0)
        self.assertEqual(out["net_income"][1]["value"], -346028278.0)

    def test_source_document_sha256_fingerprints_exact_bytes(self):
        raw = b"%PDF-1.4\nCaracasBull fixture\n"
        self.assertEqual(source_document_sha256(raw), hashlib.sha256(raw).hexdigest())
        self.assertIsNone(source_document_sha256(b""))

    def test_does_not_invent_missing_fields(self):
        out = extract_candidates_from_pages(["Documento sin cifras financieras reconocibles"])
        self.assertEqual(out, {})

    def test_parentheses_are_negative(self):
        out = extract_candidates_from_pages(["Pérdida neta (1.250,75)"])
        self.assertLess(out["net_income"][0]["value"], 0)


if __name__ == "__main__":
    unittest.main()
