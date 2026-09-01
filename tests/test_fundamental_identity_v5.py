import unittest

from database import Base, FundamentalDocument, FundamentalSnapshot, SessionLocal, engine
from services.fundamental_identity_v5 import economic_payload, economic_signature
from services.fundamental_store_v5 import save_snapshot


class FundamentalIdentityV5Tests(unittest.TestCase):
    SOURCE = "https://www.msf.com/test-economic-identity-v5.pdf"
    AS_OF = "2021-12-31"

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)

    def setUp(self):
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        with SessionLocal() as db:
            docs = db.query(FundamentalDocument).filter(
                FundamentalDocument.source_url == self.SOURCE
            ).all()
            ids = [d.id for d in docs]
            if ids:
                db.query(FundamentalSnapshot).filter(
                    FundamentalSnapshot.document_id.in_(ids)
                ).delete(synchronize_session=False)
                db.query(FundamentalDocument).filter(
                    FundamentalDocument.id.in_(ids)
                ).delete(synchronize_session=False)
                db.commit()

    @staticmethod
    def _payload(**overrides):
        payload = {
            "industry_type": "financial",
            "currency": "VES",
            "monetary_basis": "nominal_ves",
            "total_assets": 1_000_000.0,
            "equity": 250_000.0,
            "net_income": 80_000.0,
            "fx_rate_bcv_close": 4.60,
            "fx_rate_bcv_avg": 4.20,
            "total_assets_usd": 217_391.30,
            "equity_usd": 54_347.83,
            "net_income_usd": 19_047.62,
            "market_cap": 900_000.0,
            "valuation_as_of": "2026-09-01",
            "market_fx_rate_bcv": 700.0,
        }
        payload.update(overrides)
        return payload

    def test_economic_payload_excludes_fx_usd_and_market_valuation(self):
        stable = economic_payload(self._payload())
        self.assertNotIn("fx_rate_bcv_close", stable)
        self.assertNotIn("total_assets_usd", stable)
        self.assertNotIn("market_cap", stable)
        self.assertNotIn("valuation_as_of", stable)
        self.assertEqual(stable["total_assets"], 1_000_000.0)
        self.assertEqual(stable["net_income"], 80_000.0)

    def test_signature_ignores_derived_changes_but_detects_reported_change(self):
        first = self._payload()
        derived_changed = self._payload(
            fx_rate_bcv_close=9.99,
            fx_rate_bcv_avg=8.88,
            total_assets_usd=100_000.0,
            equity_usd=25_000.0,
            net_income_usd=8_000.0,
            market_cap=1_800_000.0,
            market_fx_rate_bcv=999.0,
        )
        reported_changed = self._payload(net_income=81_000.0)

        sig1 = economic_signature(self.SOURCE, self.AS_OF, first)
        self.assertEqual(sig1, economic_signature(self.SOURCE, self.AS_OF, derived_changed))
        self.assertNotEqual(sig1, economic_signature(self.SOURCE, self.AS_OF, reported_changed))

    def test_signature_normalizes_numeric_and_context_formatting(self):
        first = self._payload()
        reformatted = self._payload(
            total_assets="1000000",
            equity="250000.0",
            net_income="80000",
            currency=" ves ",
            monetary_basis=" NOMINAL_VES ",
            industry_type=" FINANCIAL ",
        )
        self.assertEqual(
            economic_signature(self.SOURCE, self.AS_OF, first),
            economic_signature(self.SOURCE, self.AS_OF, reformatted),
        )

    def test_save_snapshot_recognizes_legacy_economic_duplicate(self):
        first = save_snapshot(
            "MVZ.A",
            self._payload(),
            source_url=self.SOURCE,
            as_of=self.AS_OF,
            document_type="test_fixture",
            fiscal_period="FY2021",
            audited=False,
        )
        self.assertTrue(first.get("saved"))
        first_id = first.get("document_id")

        second = save_snapshot(
            "MVZ.A",
            self._payload(
                fx_rate_bcv_close=99.0,
                fx_rate_bcv_avg=88.0,
                total_assets_usd=10_101.01,
                equity_usd=2_525.25,
                net_income_usd=909.09,
                market_cap=2_000_000.0,
                market_fx_rate_bcv=1_000.0,
            ),
            source_url=self.SOURCE,
            as_of=self.AS_OF,
            document_type="test_fixture",
            fiscal_period="FY2021",
            audited=False,
            metadata={"normalization_revision": "second-pass"},
        )

        self.assertFalse(second.get("saved"))
        self.assertTrue(second.get("duplicate"))
        self.assertTrue(second.get("economic_duplicate"))
        self.assertEqual(second.get("document_id"), first_id)

        with SessionLocal() as db:
            count = db.query(FundamentalDocument).filter(
                FundamentalDocument.source_url == self.SOURCE,
                FundamentalDocument.as_of == self.AS_OF,
            ).count()
            self.assertEqual(count, 1)

    def test_reported_change_creates_new_economic_version(self):
        first = save_snapshot(
            "MVZ.A",
            self._payload(),
            source_url=self.SOURCE,
            as_of=self.AS_OF,
            document_type="test_fixture",
            fiscal_period="FY2021",
        )
        second = save_snapshot(
            "MVZ.A",
            self._payload(net_income=81_000.0),
            source_url=self.SOURCE,
            as_of=self.AS_OF,
            document_type="test_fixture",
            fiscal_period="FY2021",
        )

        self.assertTrue(first.get("saved"))
        self.assertTrue(second.get("saved"))
        self.assertNotEqual(first.get("document_id"), second.get("document_id"))


if __name__ == "__main__":
    unittest.main()
