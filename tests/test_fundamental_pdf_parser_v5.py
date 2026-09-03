import hashlib
import unittest

from services.fundamental_pdf_parser_v5 import _official_host_allowed, extract_candidates_from_pages, source_document_sha256


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

    def test_single_dot_three_digits_is_thousands_not_decimal(self):
        out = extract_candidates_from_pages([
            "Total activos 931.194 850.125\nTotal pasivos 500.000 450.000\nPatrimonio 431.194 400.125"
        ])
        self.assertEqual(out["total_assets"][0]["value"], 931194.0)
        self.assertEqual(out["total_assets"][1]["value"], 850125.0)

    def test_us_grouped_numbers_are_one_token(self):
        out = extract_candidates_from_pages([
            "Total activos 223,342,270.07 201,100,000.25\n"
            "Total pasivos 120,000,000.00 110,000,000.00\n"
            "Patrimonio 103,342,270.07 91,100,000.25"
        ])
        self.assertAlmostEqual(out["total_assets"][0]["value"], 223342270.07)
        self.assertAlmostEqual(out["total_assets"][1]["value"], 201100000.25)
        self.assertEqual(out["total_assets"][0]["raw"], "223,342,270.07")

    def test_simple_decimal_remains_decimal(self):
        out = extract_candidates_from_pages(["Resultado neto 270.07 120,50"])
        self.assertAlmostEqual(out["net_income"][0]["value"], 270.07)
        self.assertAlmostEqual(out["net_income"][1]["value"], 120.50)

    def test_derives_totals_only_from_same_page_same_column_components(self):
        out = extract_candidates_from_pages([
            "Notas 2025 2024\n"
            "Total activos corrientes 650.000.000 700.000.000\n"
            "Total activos no corrientes 350.000.000 300.000.000\n"
            "Total pasivos corrientes 200.000.000 250.000.000\n"
            "Total pasivos no corrientes 100.000.000 100.000.000\n"
            "Total patrimonio 700.000.000 650.000.000"
        ])
        derived_assets = [x for x in out["total_assets"] if x.get("context_quality") == "derived_accounting_total"]
        derived_liabilities = [x for x in out["total_liabilities"] if x.get("context_quality") == "derived_accounting_total"]
        self.assertEqual([x["value"] for x in derived_assets], [1000000000.0, 1000000000.0])
        self.assertEqual([x["value"] for x in derived_liabilities], [300000000.0, 350000000.0])
        self.assertEqual(derived_assets[0]["page_years"][:2], [2025, 2024])
        self.assertEqual(derived_assets[0]["derived_from"], ["assets_current", "assets_noncurrent"])

    def test_ocr_space_after_thousands_dot_is_repaired(self):
        out = extract_candidates_from_pages(["Resultado neto (404. 499.712) (346.028.278)"])
        self.assertEqual(out["net_income"][0]["value"], -404499712.0)
        self.assertEqual(out["net_income"][1]["value"], -346028278.0)

    def test_ocr_note_reference_before_columns_is_not_a_value(self):
        out = extract_candidates_from_pages([
            "Efectivo en caja y bancos 13 9.929.899 2.453.517\n"
            "Resultado neto 7 54.780.803 61.757.064"
        ])
        self.assertEqual([x["value"] for x in out["cash"][:2]], [9929899.0, 2453517.0])
        self.assertEqual([x["column_index"] for x in out["cash"][:2]], [0, 1])
        self.assertEqual([x["value"] for x in out["net_income"][:2]], [54780803.0, 61757064.0])

    def test_per_share_result_does_not_replace_net_income(self):
        out = extract_candidates_from_pages([
            "Utilidad (pérdida) neta integral por acción 15 1,39 0,58\n"
            "Utilidad (pérdida) neta 48.500.000 31.200.000"
        ])
        self.assertEqual([x["value"] for x in out["net_income"][:2]], [48500000.0, 31200000.0])

    def test_ocr_comma_in_net_income_label_is_supported(self):
        out = extract_candidates_from_pages([
            "Total patrimonio neto 310.898.831 138.464.333\n"
            "Utilidad, neta 85.201.971 196.946.156"
        ])
        self.assertEqual(out["equity"][0]["value"], 310898831.0)
        self.assertEqual(out["net_income"][0]["value"], 85201971.0)

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

    def test_single_spanish_thousands_separator_is_not_decimal(self):
        out = extract_candidates_from_pages(["Total activo 1.250"])
        self.assertEqual(out["total_assets"][0]["value"], 1250)

    def test_detects_statement_scale_on_candidate_page(self):
        out = extract_candidates_from_pages([
            "Estados financieros en miles de bolívares constantes Total activo 1.250 Total pasivo 500 Total patrimonio 750"
        ])
        self.assertEqual(out["total_assets"][0]["page_value_multiplier"], 1000)
        self.assertEqual(out["total_assets"][0]["page_monetary_basis"], "constant_ves_end_period")

    def test_marks_bnc_consolidated_and_venezuela_statement_scopes(self):
        out = extract_candidates_from_pages([
            "CONSOLIDADO CON SUCURSALES EN EL EXTERIOR\nTOTAL DEL ACTIVO 100 90",
            "BALANCE DE OPERACIONES EN VENEZUELA\nTOTAL DEL ACTIVO 80 70",
        ])
        self.assertEqual(out["total_assets"][0]["page_scope"], "bnc_consolidated_foreign_branches")
        self.assertEqual(out["total_assets"][2]["page_scope"], "bnc_venezuela_operations")

    def test_registered_primary_and_cdn_hosts_only(self):
        self.assertTrue(_official_host_allowed("BNC", "https://www.bncenlinea.com/report.pdf"))
        self.assertTrue(_official_host_allowed("BNC", "https://d3q4nr72nuserl.cloudfront.net/report.pdf"))
        self.assertFalse(_official_host_allowed("BNC", "https://evil.example/report.pdf"))
        self.assertFalse(_official_host_allowed("BNC", "https://com/report.pdf"))


if __name__ == "__main__":
    unittest.main()
