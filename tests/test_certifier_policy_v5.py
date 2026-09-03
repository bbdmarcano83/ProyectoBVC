import unittest
from unittest.mock import patch

from services.fundamental_certifier_policy_v5 import (
    CERTIFIERS,
    CERTIFIER_POLICY_VERSION,
    certify_fundamental_source,
    classify_fundamental_source,
    resolve_certified_evidence,
)
from services.fundamental_collector_v5 import ingest_normalized_report


MPA_SECONDARY = "https://es.marketscreener.com/noticias/manpa-estados-financieros-auditados-2024-2023"
CCR_SECONDARY_A = "https://es.marketscreener.com/noticias/ceramica-carabobo-estados-financieros"
CCR_SECONDARY_B = "https://wtcasadebolsa.com/ceramica-carabobo-estados-financieros/"


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
        self.assertEqual(result["evidence_tier"], "A_CERTIFIED")

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

    def test_curated_secondary_is_not_certified_but_is_admissible(self):
        certified = certify_fundamental_source("MPA", MPA_SECONDARY)
        self.assertFalse(certified["valid"])
        result = classify_fundamental_source("MPA", MPA_SECONDARY)
        self.assertTrue(result["admissible"])
        self.assertFalse(result["certified"])
        self.assertEqual(result["evidence_tier"], "B_SECONDARY")
        self.assertEqual(result["evidence_confidence"], 70)

    def test_arbitrary_https_secondary_is_not_admissible(self):
        result = classify_fundamental_source("MPA", "https://example.com/informe.pdf")
        self.assertFalse(result["admissible"])
        self.assertEqual(result["reason"], "secondary_source_not_registered_for_symbol")

    def test_non_https_secondary_is_not_admissible(self):
        result = classify_fundamental_source("MPA", "http://es.marketscreener.com/informe.pdf")
        self.assertFalse(result["admissible"])

    def test_lookalike_authority_hosts_are_not_certified_or_secondary(self):
        result = classify_fundamental_source(
            "PIV.B", "https://bolsadecaracas.com.attacker.invalid/informe.pdf"
        )
        self.assertFalse(result["certified"])
        self.assertFalse(result["admissible"])
        result = classify_fundamental_source(
            "PIV.B", "https://sunaval.gob.ve.attacker.invalid/informe.pdf"
        )
        self.assertFalse(result["certified"])
        self.assertFalse(result["admissible"])

    def test_collector_accepts_curated_secondary_fundamental(self):
        with patch("services.fundamental_collector_v5.save_snapshot", return_value={"saved": True, "duplicate": False, "document_id": 1, "snapshot_id": 2}):
            result = ingest_normalized_report(
                "MPA",
                {"currency": "USD", "total_assets": 100, "total_liabilities": 40, "equity": 60, "net_income": 10},
                source_url=MPA_SECONDARY,
                as_of="2024-12-31",
                document_type="secondary_financial_report",
                fiscal_period="FY2024",
                require_fx=False,
            )
        self.assertTrue(result["accepted"])
        self.assertTrue(result["asset_evaluable"])
        self.assertEqual(result["certification"]["evidence_tier"], "B_SECONDARY")

    def test_certified_value_beats_secondary_candidate(self):
        result = resolve_certified_evidence("MPA", [
            {"value": 100, "source_url": MPA_SECONDARY},
            {"value": 125, "source_url": "https://www.bolsadecaracas.com/manpa-auditado/"},
        ])
        self.assertTrue(result["valid"])
        self.assertEqual(result["value"], 125)
        self.assertEqual(result["certifiers"], ["bvc"])
        self.assertEqual(result["evidence_tier"], "A_CERTIFIED")
        self.assertEqual(len(result["secondary"]), 1)

    def test_secondary_candidate_can_fill_when_no_certified_evidence_exists(self):
        result = resolve_certified_evidence("MPA", [
            {"value": 999, "source_url": MPA_SECONDARY},
        ])
        self.assertTrue(result["valid"])
        self.assertEqual(result["value"], 999)
        self.assertEqual(result["evidence_tier"], "B_SECONDARY")
        self.assertEqual(result["evidence_confidence"], 70)

    def test_conflicting_secondary_values_fail_closed_for_fundamental_only(self):
        result = resolve_certified_evidence("CCR", [
            {"value": 100, "source_url": CCR_SECONDARY_A},
            {"value": 101, "source_url": CCR_SECONDARY_B},
        ])
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "secondary_evidence_conflict")

    def test_conflicting_certified_authorities_fail_closed(self):
        result = resolve_certified_evidence("PIV.B", [
            {"value": 125, "source_url": "https://pivca.com/wp-content/uploads/auditado.pdf"},
            {"value": 126, "source_url": "https://www.sunaval.gob.ve/documentos/auditado.pdf"},
        ])
        self.assertFalse(result["valid"])
        self.assertIsNone(result["value"])
        self.assertEqual(result["reason"], "certified_authority_conflict")
        self.assertEqual(len(result["certified"]), 2)

    def test_matching_certified_authorities_are_joint_provenance(self):
        result = resolve_certified_evidence("PIV.B", [
            {"value": 125, "source_url": "https://pivca.com/wp-content/uploads/auditado.pdf"},
            {"value": 125, "source_url": "https://www.bolsadecaracas.com/pivca-auditado/"},
        ])
        self.assertTrue(result["valid"])
        self.assertEqual(result["value"], 125)
        self.assertEqual(result["certifiers"], ["bvc", "issuer"])


if __name__ == "__main__":
    unittest.main()
