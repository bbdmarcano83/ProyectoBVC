import unittest

from services.fundamental_document_metadata_v5 import (
    _official_host_allowed,
    infer_document_metadata_from_pages,
)


class FundamentalDocumentMetadataV5Tests(unittest.TestCase):
    def test_resolves_constant_ves_audited_annual_statement(self):
        pages = [
            "INFORME DE LOS CONTADORES PÚBLICOS INDEPENDIENTES\n"
            "Estados financieros auditados\n"
            "Estado de situación financiera al 31 de diciembre de 2025 y 31 de diciembre de 2024\n"
            "Cifras expresadas en bolívares constantes de poder adquisitivo a la fecha",
        ]
        meta = infer_document_metadata_from_pages(pages)
        self.assertTrue(meta["resolved"])
        self.assertEqual(meta["as_of"], "2025-12-31")
        self.assertEqual(meta["fiscal_period"], "FY2025")
        self.assertEqual(meta["currency"], "VES")
        self.assertEqual(meta["monetary_basis"], "constant_ves_end_period")
        self.assertTrue(meta["audited"])

    def test_nominal_ves_requires_explicit_nominal_wording(self):
        unresolved = infer_document_metadata_from_pages([
            "Estados financieros auditados al 31 de diciembre de 2025 expresados en bolívares"
        ])
        self.assertEqual(unresolved["currency"], "VES")
        self.assertIsNone(unresolved["monetary_basis"])
        self.assertIn("monetary_basis", unresolved["unresolved"])

        resolved = infer_document_metadata_from_pages([
            "Estados financieros auditados al 31 de diciembre de 2025. Cifras nominales expresadas en bolívares. "
            "Informe del auditor independiente"
        ])
        self.assertEqual(resolved["monetary_basis"], "nominal_ves")

    def test_mixed_usd_and_ves_fails_currency_closed(self):
        meta = infer_document_metadata_from_pages([
            "Informe del auditor independiente. Estado al 31 de diciembre de 2025. "
            "Cifras expresadas en bolívares. Nota: ciertos contratos están denominados en USD."
        ])
        self.assertIsNone(meta["currency"])
        self.assertIn("currency", meta["unresolved"])

    def test_comparative_same_page_chooses_latest_explicit_date(self):
        meta = infer_document_metadata_from_pages([
            "Informe del auditor independiente. Estado de situación financiera al 31 de diciembre de 2025 y al 31 de diciembre de 2024. "
            "Cifras nominales expresadas en bolívares."
        ])
        self.assertEqual(meta["as_of"], "2025-12-31")

    def test_does_not_infer_published_at(self):
        meta = infer_document_metadata_from_pages([
            "Estados financieros auditados al 31 de diciembre de 2025. "
            "Cifras nominales expresadas en bolívares. Informe de auditoría independiente."
        ])
        self.assertNotIn("published_at", meta)
        self.assertIn("published_at", meta["note"])

    def test_registered_issuer_document_cdn_is_allowed(self):
        url = (
            "https://d3q4nr72nuserl.cloudfront.net/docs/default-source/documents/"
            "finalcial-reports/annual-reports/diciembre-2025.pdf"
        )
        self.assertTrue(_official_host_allowed("BNC", url))
        self.assertFalse(_official_host_allowed("BPV", url))


if __name__ == "__main__":
    unittest.main()
