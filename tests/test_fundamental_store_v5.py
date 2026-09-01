import unittest

from database import init_db
from services.fundamental_store_v5 import (
    validate_snapshot,
    validate_document_dates,
    is_document_available_on,
    save_snapshot,
    load_latest_validated,
    load_validated_as_of,
)


class FundamentalStoreV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def _payload(self, net_income=35):
        return {
            "currency": "USD",
            "industry_type": "financial",
            "total_assets": 1000,
            "total_liabilities": 800,
            "equity": 200,
            "net_income": net_income,
            "market_cap": 420,
            "earnings_history": [20, 25, 30, net_income],
        }

    def test_registered_source_and_accounting_equation_pass(self):
        out = validate_snapshot(
            "BNC", self._payload(),
            "https://www.bncenlinea.com/bnc/informes-anuales", "2099-12-31"
        )
        self.assertTrue(out["valid"])
        self.assertEqual(out["accounting_error_pct"], 0.0)
        self.assertEqual(out["industry_type"], "financial")

    def test_incomplete_as_of_is_rejected(self):
        out = validate_snapshot(
            "BNC", self._payload(),
            "https://www.bncenlinea.com/bnc/informes-anuales", "2099-12"
        )
        self.assertFalse(out["valid"])
        self.assertIn("YYYY-MM-DD", out["notes"][0])

    def test_publication_cannot_precede_statement_date(self):
        out = validate_document_dates("2099-12-31", "2099-12-30")
        self.assertFalse(out["valid"])
        self.assertIn("published_before_as_of", out["flags"])

    def test_publication_date_can_be_iso_timestamp(self):
        out = validate_document_dates("2099-12-31", "2100-02-15T10:30:00+00:00")
        self.assertTrue(out["valid"])
        self.assertEqual(out["published_date"], "2100-02-15")

    def test_document_availability_fails_closed_when_publication_unknown(self):
        self.assertFalse(is_document_available_on(None, "2100-01-15"))
        self.assertFalse(is_document_available_on("2100-02-01", "2100-01-15"))
        self.assertTrue(is_document_available_on("2100-01-01", "2100-01-15"))

    def test_unmapped_symbol_fails_closed(self):
        out = validate_snapshot("ZZZ", self._payload(), "https://example.com/a.pdf", "2099-12-31")
        self.assertFalse(out["valid"])
        self.assertEqual(out["score"], 0.0)

    def test_bad_accounting_equation_is_rejected(self):
        p = self._payload()
        p["equity"] = 500
        out = validate_snapshot(
            "BNC", p,
            "https://www.bncenlinea.com/bnc/informes-anuales", "2099-11-30"
        )
        self.assertFalse(out["valid"])
        self.assertGreater(out["accounting_error_pct"], 5)

    def test_save_is_idempotent_and_loads_latest_validated(self):
        url = "https://www.bncenlinea.com/bnc/informes-anuales"
        first = save_snapshot(
            "BNC", self._payload(), source_url=url, as_of="2099-12-31",
            document_type="annual_report", fiscal_period="FY2099", audited=True,
            published_at="2100-02-15",
        )
        self.assertIn(first.get("saved"), {True, False})
        second = save_snapshot(
            "BNC", self._payload(), source_url=url, as_of="2099-12-31",
            document_type="annual_report", fiscal_period="FY2099", audited=True,
            published_at="2100-02-15",
        )
        self.assertFalse(second["saved"])
        self.assertTrue(second["duplicate"])

        payload, meta = load_latest_validated()
        self.assertIn("BNC", payload)
        self.assertTrue(meta["available"])
        self.assertEqual(payload["BNC"]["as_of"], "2099-12-31")
        self.assertTrue(payload["BNC"]["audited"])

    def test_duplicate_can_enrich_missing_source_sha_but_never_overwrite_conflict(self):
        url = "https://www.bncenlinea.com/bnc/informes-anuales"
        sha_a = "a" * 64
        sha_b = "b" * 64
        base = save_snapshot(
            "BNC", self._payload(31), source_url=url, as_of="2096-12-31",
            document_type="annual_report", fiscal_period="FY2096", audited=True,
            published_at="2097-02-01",
        )
        self.assertIn(base.get("saved"), {True, False})

        enriched = save_snapshot(
            "BNC", self._payload(31), source_url=url, as_of="2096-12-31",
            document_type="annual_report", fiscal_period="FY2096", audited=True,
            published_at="2097-02-01", metadata={"source_document_sha256": sha_a},
        )
        self.assertTrue(enriched["duplicate"])
        self.assertEqual(enriched["source_document_sha256"], sha_a)

        conflict = save_snapshot(
            "BNC", self._payload(31), source_url=url, as_of="2096-12-31",
            document_type="annual_report", fiscal_period="FY2096", audited=True,
            published_at="2097-02-01", metadata={"source_document_sha256": sha_b},
        )
        self.assertFalse(conflict["duplicate"])
        self.assertTrue(conflict["source_document_hash_conflict"])
        self.assertEqual(conflict["existing_source_document_sha256"], sha_a)
        self.assertEqual(conflict["incoming_source_document_sha256"], sha_b)

    def test_backtest_loader_blocks_future_publication_and_future_history(self):
        url = "https://www.bncenlinea.com/bnc/informes-anuales"
        save_snapshot(
            "BNC", self._payload(30), source_url=url, as_of="2098-12-31",
            document_type="annual_report", fiscal_period="FY2098", audited=True,
            published_at="2099-02-15",
        )
        save_snapshot(
            "BNC", self._payload(35), source_url=url, as_of="2099-12-31",
            document_type="annual_report", fiscal_period="FY2099", audited=True,
            published_at="2100-02-15",
        )

        before_release, meta = load_validated_as_of("2100-01-15")
        self.assertIn("BNC", before_release)
        self.assertEqual(before_release["BNC"]["as_of"], "2098-12-31")
        self.assertTrue(meta["no_lookahead"])
        self.assertGreaterEqual(meta["skipped_future_or_unavailable"], 1)

        after_release, _ = load_validated_as_of("2100-03-01")
        self.assertEqual(after_release["BNC"]["as_of"], "2099-12-31")

    def test_save_rejects_publication_before_close(self):
        out = save_snapshot(
            "BNC", self._payload(),
            source_url="https://www.bncenlinea.com/bnc/informes-anuales",
            as_of="2097-12-31", document_type="annual_report", fiscal_period="FY2097",
            audited=True, published_at="2097-12-01",
        )
        self.assertFalse(out["saved"])
        self.assertIn("published_before_as_of", out["validation"]["notes"])


if __name__ == "__main__":
    unittest.main()
