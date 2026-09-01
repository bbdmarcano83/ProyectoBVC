import unittest

from database import init_db, SessionLocal
from services.ibc_store_v5 import ensure_ibc_schema, persist_ibc_points, load_persisted_ibc, IBC_HISTORY_V5


class IBCStoreV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        ensure_ibc_schema()

    def setUp(self):
        with SessionLocal() as db:
            db.execute(IBC_HISTORY_V5.delete())
            db.commit()

    def test_secondary_can_fill_missing_date(self):
        out = persist_ibc_points([{
            "date": "2025-12-30", "close": 100,
            "source_url": "https://datosmacro.expansion.com/bolsa/venezuela",
        }])
        self.assertEqual(out["inserted"], 1)
        points, meta = load_persisted_ibc()
        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["source_confidence"], 75)
        self.assertEqual(meta["official_points"], 0)

    def test_official_replaces_secondary_same_date(self):
        persist_ibc_points([{
            "date": "2025-12-30", "close": 100,
            "source_url": "https://datosmacro.expansion.com/bolsa/venezuela",
        }])
        out = persist_ibc_points([{
            "date": "2025-12-30", "close": 101,
            "source_url": "https://www.bolsadecaracas.com/resumen",
        }])
        self.assertEqual(out["updated"], 1)
        points, _ = load_persisted_ibc()
        self.assertAlmostEqual(points[0]["close"], 101)
        self.assertTrue(points[0]["source_official"])

    def test_secondary_never_downgrades_official(self):
        persist_ibc_points([{
            "date": "2025-12-30", "close": 101,
            "source_url": "https://www.bolsadecaracas.com/resumen",
        }])
        out = persist_ibc_points([{
            "date": "2025-12-30", "close": 99,
            "source_url": "https://datosmacro.expansion.com/bolsa/venezuela",
        }])
        self.assertEqual(out["unchanged"], 1)
        points, _ = load_persisted_ibc()
        self.assertAlmostEqual(points[0]["close"], 101)
        self.assertTrue(points[0]["source_official"])

    def test_unknown_source_is_rejected(self):
        out = persist_ibc_points([{
            "date": "2025-12-30", "close": 101,
            "source_url": "https://example.com/value",
        }])
        self.assertEqual(out["rejected"], 1)
        points, _ = load_persisted_ibc()
        self.assertEqual(points, [])


if __name__ == "__main__":
    unittest.main()
