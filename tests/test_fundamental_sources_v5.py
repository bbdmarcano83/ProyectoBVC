import unittest

from services.fundamental_sources_v5 import get_source, source_audit_summary


class FundamentalSourceRegistryTests(unittest.TestCase):
    def test_aliases_share_same_issuer(self):
        self.assertEqual(get_source("MVZ.B")["canonical_symbol"], "MVZ.A")
        self.assertEqual(get_source("RST.B")["canonical_symbol"], "RST")
        self.assertEqual(get_source("PIV.A")["canonical_symbol"], "PIV.B")
        self.assertEqual(get_source("IVC.B")["canonical_symbol"], "IVC.A")
        self.assertEqual(get_source("ARC.B")["canonical_symbol"], "ARC.A")

    def test_financials_are_flagged_for_bank_model(self):
        for symbol in ("MVZ.A", "BNC", "BPV", "BVL", "ABC.A"):
            self.assertEqual(get_source(symbol)["industry_type"], "financial")
            self.assertEqual(get_source(symbol)["status"], "verified_primary")

    def test_investment_vehicles_use_dedicated_model(self):
        for symbol in ("ICP.B", "PER", "MTC.B", "CCP.B", "PCP.B", "VNA.B"):
            src = get_source(symbol)
            self.assertIsNotNone(src)
            self.assertEqual(src["industry_type"], "investment_vehicle")

    def test_observed_bvc_board_has_source_route(self):
        observed = (
            "BPV", "TPG", "BVCC", "TDV.D", "RST.B", "BNC", "PGR", "PIV.B",
            "MPA", "PCP.B", "EFE", "RST", "FNV", "ENV", "IVC.B", "CCP.B",
            "GZL", "ICP.B", "SVS", "BVL", "MVZ.B", "PTN", "CRM.A", "FNC",
            "DOM", "CGQ", "MTC.B", "ABC.A", "IVC.A", "MVZ.A", "CCR", "GMC.B",
            "ARC.B", "VNA.B",
        )
        audit = source_audit_summary(list(observed))
        self.assertEqual(audit["symbols"], len(observed))
        self.assertEqual(audit["covered"], len(observed))
        self.assertEqual(audit["coverage_pct"], 100.0)
        self.assertFalse([row for row in audit["rows"] if not row["covered"]])

    def test_unknown_symbol_fails_closed(self):
        self.assertIsNone(get_source("NOEXISTE"))

    def test_audit_summary_reports_unmapped(self):
        out = source_audit_summary(["MVZ.A", "SVS", "NOEXISTE"])
        self.assertEqual(out["symbols"], 3)
        self.assertEqual(out["covered"], 2)
        self.assertEqual(out["rows"][-1]["status"], "unmapped")


if __name__ == "__main__":
    unittest.main()
