import unittest

from services.fundamental_sources_v5 import get_source, source_audit_summary


class FundamentalSourceRegistryTests(unittest.TestCase):
    def test_aliases_share_same_issuer(self):
        self.assertEqual(get_source("MVZ.B")["canonical_symbol"], "MVZ.A")
        self.assertEqual(get_source("RST.B")["canonical_symbol"], "RST")
        self.assertEqual(get_source("PIV.A")["canonical_symbol"], "PIV.B")

    def test_financials_are_flagged_for_bank_model(self):
        for symbol in ("MVZ.A", "BNC", "BPV", "BVL", "ABC.A"):
            self.assertEqual(get_source(symbol)["industry_type"], "financial")
            self.assertEqual(get_source(symbol)["status"], "verified_primary")

    def test_unknown_symbol_fails_closed(self):
        self.assertIsNone(get_source("NOEXISTE"))

    def test_audit_summary_reports_unmapped(self):
        out = source_audit_summary(["MVZ.A", "SVS", "NOEXISTE"])
        self.assertEqual(out["symbols"], 3)
        self.assertEqual(out["covered"], 2)
        self.assertEqual(out["rows"][-1]["status"], "unmapped")


if __name__ == "__main__":
    unittest.main()
