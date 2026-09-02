import unittest

from services.fundamental_regulatory_manifest_v5 import (
    AUTHORITATIVE_MARKET_HOSTS,
    REGULATORY_BACKFILL_V5,
    classify_authoritative_url,
    regulatory_manifest_summary,
)
from services.fundamental_sources_v5 import source_url_allowed


class RegulatoryFundamentalSourcesV5Tests(unittest.TestCase):
    def test_bvc_and_sunaval_are_authoritative_https_sources(self):
        bvc = classify_authoritative_url("https://www.bolsadecaracas.com/mercado")
        sunaval = classify_authoritative_url("https://www.sunaval.gob.ve/documento.pdf")
        self.assertTrue(bvc["official"])
        self.assertEqual(bvc["authority"], "BVC")
        self.assertEqual(bvc["confidence"], 100)
        self.assertTrue(sunaval["official"])
        self.assertEqual(sunaval["authority"], "SUNAVAL")
        self.assertEqual(sunaval["confidence"], 100)
        self.assertIn("bolsadecaracas.com", AUTHORITATIVE_MARKET_HOSTS)
        self.assertIn("sunaval.gob.ve", AUTHORITATIVE_MARKET_HOSTS)

    def test_authority_classification_fails_closed(self):
        self.assertFalse(classify_authoritative_url("http://www.sunaval.gob.ve/x")["official"])
        self.assertFalse(classify_authoritative_url("https://sunaval.gob.ve.attacker.invalid/x")["official"])
        self.assertFalse(classify_authoritative_url("https://example.com/x")["official"])

    def test_pivb_fy2025_is_registered_and_issuer_official(self):
        summary = regulatory_manifest_summary()
        self.assertEqual(summary["issuers"], 1)
        self.assertEqual(summary["documents"], 1)
        doc = REGULATORY_BACKFILL_V5["PIV.B"]["documents"][0]
        self.assertEqual(doc["fiscal_period"], "FY2025")
        self.assertEqual(doc["monetary_basis"], "nominal_ves")
        self.assertTrue(doc["audited"])
        self.assertTrue(source_url_allowed("PIV.B", doc["url"]))
        self.assertIn("sunaval_registration", doc["regulatory_evidence"])


if __name__ == "__main__":
    unittest.main()
