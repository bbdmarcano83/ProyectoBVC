import unittest

from services.fundamental_pilots_v5 import PILOTS
from services.fundamental_sources_v5 import get_source
from services.fundamental_store_v5 import validate_snapshot


class FundamentalPilotV5Tests(unittest.TestCase):
    def test_three_model_families_are_represented(self):
        self.assertEqual(get_source("MVZ.A")["industry_type"], "financial")
        self.assertEqual(get_source("SVS")["industry_type"], "non_financial")
        self.assertEqual(get_source("ICP.B")["industry_type"], "investment_vehicle")
        self.assertEqual(get_source("GZL")["industry_type"], "investment_vehicle")

    def test_pilot_sources_are_official_https(self):
        for symbol, item in PILOTS.items():
            self.assertTrue(item["source_url"].startswith("https://"), symbol)
            self.assertGreaterEqual(get_source(symbol)["confidence"], 100, symbol)

    def test_all_pilot_snapshots_pass_fail_closed_validator(self):
        for symbol, item in PILOTS.items():
            out = validate_snapshot(symbol, item["data"], item["source_url"], item["as_of"])
            self.assertTrue(out["valid"], f"{symbol}: {out}")
            self.assertGreaterEqual(out["score"], 70.0, symbol)

    def test_audited_flags_are_not_invented(self):
        self.assertFalse(PILOTS["MVZ.A"]["audited"])
        self.assertTrue(PILOTS["SVS"]["audited"])
        self.assertTrue(PILOTS["ICP.B"]["audited"])


if __name__ == "__main__":
    unittest.main()
