import unittest

from database import init_db
from services.fundamental_store_v5 import validate_snapshot, save_snapshot, load_latest_validated


class FundamentalStoreV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def _payload(self):
        return {
            "industry_type": "financial",
            "total_assets": 1000,
            "total_liabilities": 800,
            "equity": 200,
            "net_income": 35,
            "market_cap": 420,
            "earnings_history": [20, 25, 30, 35],
        }

    def test_registered_source_and_accounting_equation_pass(self):
        out = validate_snapshot(
            "BNC", self._payload(),
            "https://www.bncenlinea.com/bnc/informes-anuales", "2099-12"
        )
        self.assertTrue(out["valid"])
        self.assertEqual(out["accounting_error_pct"], 0.0)
        self.assertEqual(out["industry_type"], "financial")

    def test_unmapped_symbol_fails_closed(self):
        out = validate_snapshot("ZZZ", self._payload(), "https://example.com/a.pdf", "2099-12")
        self.assertFalse(out["valid"])
        self.assertEqual(out["score"], 0.0)

    def test_bad_accounting_equation_is_rejected(self):
        p = self._payload()
        p["equity"] = 500
        out = validate_snapshot(
            "BNC", p,
            "https://www.bncenlinea.com/bnc/informes-anuales", "2099-11"
        )
        self.assertFalse(out["valid"])
        self.assertGreater(out["accounting_error_pct"], 5)

    def test_save_is_idempotent_and_loads_latest_validated(self):
        url = "https://www.bncenlinea.com/bnc/informes-anuales"
        first = save_snapshot(
            "BNC", self._payload(), source_url=url, as_of="2099-12",
            document_type="annual_report", fiscal_period="FY2099", audited=True,
        )
        self.assertIn(first.get("saved"), {True, False})
        second = save_snapshot(
            "BNC", self._payload(), source_url=url, as_of="2099-12",
            document_type="annual_report", fiscal_period="FY2099", audited=True,
        )
        self.assertFalse(second["saved"])
        self.assertTrue(second["duplicate"])

        payload, meta = load_latest_validated()
        self.assertIn("BNC", payload)
        self.assertTrue(meta["available"])
        self.assertEqual(payload["BNC"]["as_of"], "2099-12")
        self.assertTrue(payload["BNC"]["audited"])


if __name__ == "__main__":
    unittest.main()
