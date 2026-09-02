import unittest

from database import init_db
from services.fundamental_collector_v5 import ingest_normalized_report
from services.fundamental_pilots_v5 import HISTORICAL_PILOTS, PILOTS
from services.fundamental_sources_v5 import get_source
from services.fundamental_store_v5 import validate_snapshot, load_latest_validated


class FundamentalPilotV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

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

    def test_sivensa_historical_series_has_three_separate_audited_primary_years(self):
        rows = HISTORICAL_PILOTS["SVS"]
        self.assertEqual([r["fiscal_period"] for r in rows], ["FY2024", "FY2023", "FY2022"])
        self.assertTrue(all(r["audited"] for r in rows))
        self.assertEqual([r["as_of"] for r in rows], ["2024-09-30", "2023-09-30", "2022-09-30"])
        self.assertEqual(len({r["source_url"] for r in rows}), 3)
        self.assertTrue(all(r["data"]["monetary_basis"] == "constant_ves_end_period" for r in rows))

    def test_sivensa_historical_balance_equation_is_exact(self):
        for row in HISTORICAL_PILOTS["SVS"]:
            d = row["data"]
            self.assertEqual(d["total_assets"], d["total_liabilities"] + d["equity"], row["fiscal_period"])
            out = validate_snapshot("SVS", d, row["source_url"], row["as_of"])
            self.assertTrue(out["valid"], f"{row['fiscal_period']}: {out}")

    def test_sivensa_historical_net_income_signs_are_preserved(self):
        rows = {r["fiscal_period"]: r["data"]["net_income"] for r in HISTORICAL_PILOTS["SVS"]}
        self.assertLess(rows["FY2024"], 0)
        self.assertLess(rows["FY2023"], 0)
        self.assertGreater(rows["FY2022"], 0)

    def test_end_to_end_ingestion_persists_three_validated_families_offline_fixture_mode(self):
        # Los fixtures no hacen red en CI. Producción usa los defaults
        # hydrate_fx=True + require_fx=True y por tanto falla cerrado si falta FX.
        for symbol, item in PILOTS.items():
            out = ingest_normalized_report(
                symbol,
                item["data"],
                source_url=item["source_url"],
                as_of=item["as_of"],
                document_type=item["document_type"],
                fiscal_period=item["fiscal_period"],
                audited=item["audited"],
                metadata={"pilot_fixture": True, "evidence": item["evidence"]},
                hydrate_fx=False,
                require_fx=False,
            )
            self.assertTrue(out["accepted"], f"{symbol}: {out}")
            self.assertGreaterEqual(out["validation"]["score"], 70.0, symbol)

        payload, meta = load_latest_validated()
        self.assertTrue(meta["available"])
        for symbol in PILOTS:
            canonical = get_source(symbol)["canonical_symbol"]
            self.assertIn(canonical, payload)


if __name__ == "__main__":
    unittest.main()
