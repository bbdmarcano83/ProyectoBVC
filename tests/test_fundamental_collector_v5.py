import unittest

from database import init_db
from services.fundamental_collector_v5 import normalize_record, coverage_report, ingest_normalized_report


class FundamentalCollectorV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_normalizes_known_aliases_without_imputing(self):
        out = normalize_record("BNC", {"assets":100, "liabilities":80, "shareholders_equity":20, "profit":5})
        self.assertEqual(out["total_assets"], 100)
        self.assertEqual(out["total_liabilities"], 80)
        self.assertEqual(out["equity"], 20)
        self.assertEqual(out["net_income"], 5)
        self.assertNotIn("cash", out)
        self.assertEqual(out["industry_type"], "financial")

    def test_coverage_is_type_specific(self):
        out = coverage_report("BNC", {"total_assets":100, "equity":20})
        self.assertEqual(out["industry_type"], "financial")
        self.assertIn("net_income", out["missing"])
        self.assertLess(out["coverage_pct"], 100)

    def test_ingestion_rejects_unmapped_source(self):
        out = ingest_normalized_report(
            "ZZZ", {"total_assets":100, "total_liabilities":80, "equity":20},
            source_url="https://example.com/report.pdf", as_of="2099-10", document_type="annual_report"
        )
        self.assertFalse(out["accepted"])
        self.assertFalse(out["persisted"])

    def test_ingestion_accepts_valid_registered_snapshot(self):
        out = ingest_normalized_report(
            "BNC",
            {"assets":1000, "liabilities":800, "shareholders_equity":200, "profit":40, "market_cap":500},
            source_url="https://www.bncenlinea.com/bnc/informes-anuales",
            as_of="2099-10",
            document_type="annual_report",
            audited=True,
        )
        self.assertTrue(out["accepted"])
        self.assertGreaterEqual(out["validation"]["score"], 70)
        self.assertEqual(out["coverage"]["coverage_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
