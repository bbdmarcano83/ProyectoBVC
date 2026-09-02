import unittest

from services.fundamental_backfill_manifest_v5 import FUNDAMENTAL_BACKFILL_V5, PILOT_BACKFILL_V5, full_manifest_summary, manifest_summary
from services.fundamental_sources_v5 import source_url_allowed
from services.ibc_sources_v5 import classify_source, prefer_point


class BackfillSourcePolicyV5Tests(unittest.TestCase):
    def test_pilot_manifest_covers_three_families(self):
        summary = manifest_summary()
        self.assertEqual(summary["issuers"], 3)
        self.assertGreaterEqual(summary["documents"], 10)
        self.assertIn("MVZ.A", summary["symbols"])
        self.assertIn("SVS", summary["symbols"])
        self.assertIn("ICP.B", summary["symbols"])

    def test_exact_urls_are_https_and_issuer_domains(self):
        allowed = {
            "MVZ.A": ("msf.com",),
            "SVS": ("sivensa.com.ve",),
            "ICP.B": ("crecepymes.com",),
        }
        for symbol, cfg in PILOT_BACKFILL_V5.items():
            self.assertTrue(cfg["discovery_url"].startswith("https://"))
            for doc in cfg["documents"]:
                url = doc.get("url")
                if not url:
                    self.assertTrue(doc.get("discover_from", "").startswith("https://"))
                    continue
                self.assertTrue(url.startswith("https://"), (symbol, url))
                self.assertTrue(any(domain in url.lower() for domain in allowed[symbol]), (symbol, url))

    def test_verified_manifest_has_auditable_units_and_registered_hosts(self):
        summary = full_manifest_summary()
        self.assertGreaterEqual(summary["issuers"], 14)
        self.assertGreaterEqual(summary["documents"], 44)
        for symbol, cfg in FUNDAMENTAL_BACKFILL_V5.items():
            for doc in cfg["documents"]:
                self.assertTrue(source_url_allowed(symbol, doc["url"]), (symbol, doc["url"]))
                self.assertGreater(float(doc.get("value_multiplier", 1)), 0)

    def test_ibc_source_priority_prefers_bvc_official(self):
        official = {"date": "2025-12-30", "close": 100, "source_url": "https://www.bolsadecaracas.com/resumen"}
        secondary = {"date": "2025-12-30", "close": 99, "source_url": "https://datosmacro.expansion.com/bolsa/venezuela"}
        self.assertEqual(classify_source(official["source_url"])["confidence"], 100)
        self.assertEqual(prefer_point(secondary, official), official)
        self.assertEqual(prefer_point(official, secondary), official)

    def test_unknown_ibc_source_fails_untrusted(self):
        out = classify_source("https://example.com/ibc")
        self.assertEqual(out["confidence"], 0)
        self.assertFalse(out["official"])


if __name__ == "__main__":
    unittest.main()
