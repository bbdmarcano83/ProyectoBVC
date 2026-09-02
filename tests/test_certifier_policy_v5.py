import unittest

from services.fundamental_certifier_policy_v5 import (
    CERTIFIERS,
    CERTIFIER_POLICY_VERSION,
    certify_fundamental_source,
)
from services.fundamental_collector_v5 import ingest_normalized_report


class CertifierPolicyV5Tests(unittest.TestCase):
    def test_exact_three_certifiers(self):
        self.assertEqual(CERTIFIERS, ("issuer", "bvc", "sunaval"))
        self.assertTrue(CERTIFIER_POLICY_VERSION)

    def test_registered_issuer_domain_is_certified(self):
        result = certify_fundamental_source(
            "PIV.B",
            "https://pivca.com/wp-content/uploads/informe.pdf",
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["certifier"], "issuer")

    def test_registered_issuer_cdn_is_certified_as_issuer(self):
        result = certify_fundamental_source(
            "ABC.A",
            "https://d3olc33sy92l9e.cloudfront.net/wp-content/uploads/informe.pdf",
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["certifier"], "issuer")

    def test_bvc_is_certifier_for_registered_symbol(self):
        result = certify_fundamental_source(
            "RST",
            "https://www.bolsadecaracas.com/ron-santa-teresa-informacion-financiera/",
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["certifier"], "bvc")

    def test_sunaval_is_certifier_for_registered_symbol(self):
        result = certify_fundamental_source(
            "PIV.B",
            "https://www.sunaval.gob.ve/documentos/informe.pdf",
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["certifier"], "sunaval")

    def test_secondary_https_source_never_certifies(self):
        result = certify_fundamental_source("PIV.B", "https://example.com/informe.pdf")
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "source_not_certified_by_issuer_bvc_or_sunaval")

    def test_lookalike_authority_hosts_are_rejected(self):
        self.assertFalse(certify_fundamental_source(
            "PIV.B", "https://bolsadecaracas.com.attacker.invalid/informe.pdf"
        )["valid"])
        self.assertFalse(certify_fundamental_source(
            "PIV.B", "https://sunaval.gob.ve.attacker.invalid/informe.pdf"
        )["valid"])

    def test_collector_fails_before_fx_for_non_certified_source(self):
        result = ingest_normalized_report(
            "PIV.B",
            {"currency": "VES", "total_assets": 100, "equity": 60, "net_income": 10},
            source_url="https://example.com/informe.pdf",
            as_of="2025-12-31",
            document_type="annual_audited",
            fiscal_period="FY2025",
        )
        self.assertFalse(result["accepted"])
        self.assertFalse(result["persisted"])
        self.assertEqual(result["error"], "source_certifier_required")
        self.assertEqual(result["fx"]["flags"], ["not_evaluated_due_to_source_certifier_gate"])


if __name__ == "__main__":
    unittest.main()
