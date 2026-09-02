import unittest

from scripts.audit_fundamental_documents_v5 import _combined_manifest


class RegulatoryAuditUnionV5Tests(unittest.TestCase):
    def test_combined_manifest_includes_base_and_regulatory_symbols(self):
        manifest = _combined_manifest()
        self.assertIn("MVZ.A", manifest)
        self.assertIn("PIV.B", manifest)
        periods = {
            str(doc.get("fiscal_period"))
            for doc in manifest["PIV.B"].get("documents", [])
        }
        self.assertIn("FY2025", periods)

    def test_combined_manifest_does_not_duplicate_same_period(self):
        manifest = _combined_manifest()
        for issuer in manifest.values():
            periods = [
                str(doc.get("fiscal_period"))
                for doc in issuer.get("documents", [])
                if doc.get("fiscal_period")
            ]
            self.assertEqual(len(periods), len(set(periods)))


if __name__ == "__main__":
    unittest.main()
