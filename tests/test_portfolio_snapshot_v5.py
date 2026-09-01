import unittest
from datetime import date

from database import init_db, SessionLocal, Usuario, ActivoPortafolio
from services.portfolio_snapshot_v5 import (
    ensure_snapshot_table, save_daily_snapshot, load_snapshots, PORTFOLIO_SNAPSHOTS_V5,
)


class PortfolioSnapshotV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        ensure_snapshot_table()

    def setUp(self):
        with SessionLocal() as db:
            db.execute(PORTFOLIO_SNAPSHOTS_V5.delete())
            db.query(ActivoPortafolio).delete()
            db.query(Usuario).filter(Usuario.email.like("snapshot-test-%")).delete(synchronize_session=False)
            db.commit()
            u = Usuario(nombre="Snapshot", email=f"snapshot-test-{id(self)}@example.com", password_hash="x", activo=True)
            db.add(u); db.flush()
            self.user_id = u.id
            db.add(ActivoPortafolio(
                usuario_id=u.id, simbolo="AAA", cantidad=10, precio_promedio=100,
                comision=10, registro=1, iva=16,
            ))
            db.commit()

    def test_snapshot_uses_market_price_and_fx(self):
        out = save_daily_snapshot(
            self.user_id, prices={"AAA": 150}, fx_bcv=50, ibc_level=1000,
            as_of=date(2026, 9, 1),
        )
        self.assertTrue(out["saved"])
        self.assertEqual(out["positions_count"], 1)
        self.assertAlmostEqual(out["total_market_bs"], 1500.0)
        self.assertAlmostEqual(out["total_market_usd"], 30.0)
        self.assertAlmostEqual(out["ibc_level"], 1000.0)

    def test_same_day_is_idempotent_update(self):
        first = save_daily_snapshot(
            self.user_id, prices={"AAA": 120}, fx_bcv=40, ibc_level=900,
            as_of="2026-09-01",
        )
        second = save_daily_snapshot(
            self.user_id, prices={"AAA": 130}, fx_bcv=50, ibc_level=950,
            as_of="2026-09-01",
        )
        self.assertEqual(first["action"], "created")
        self.assertEqual(second["action"], "updated")
        rows = load_snapshots(self.user_id)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["total_market_bs"], 1300.0)
        self.assertAlmostEqual(rows[0]["fx_bcv"], 50.0)
        self.assertAlmostEqual(rows[0]["ibc_level"], 950.0)

    def test_missing_price_falls_back_to_average_and_missing_fx_keeps_usd_null(self):
        out = save_daily_snapshot(
            self.user_id, prices={}, fx_bcv=None, ibc_level=None,
            as_of="2026-09-02",
        )
        self.assertAlmostEqual(out["total_market_bs"], 1000.0)
        self.assertIsNone(out["total_market_usd"])
        self.assertIsNone(out["fx_bcv"])
        self.assertIsNone(out["ibc_level"])


if __name__ == "__main__":
    unittest.main()
