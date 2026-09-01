import os
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from services.portfolio_benchmark_context_v5 import (
    FLAG_NAME,
    attach_portfolio_benchmark_v5,
)


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.rows)


class _DB:
    def __init__(self, rows):
        self.rows = rows
        self.query_calls = 0

    def query(self, *args, **kwargs):
        self.query_calls += 1
        return _Query(self.rows)


class PortfolioBenchmarkContextV5Tests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop(FLAG_NAME, None)

    def test_disabled_returns_original_summary_without_db_query(self):
        os.environ[FLAG_NAME] = "false"
        resumen = {"total": 123}
        db = _DB([])
        out = attach_portfolio_benchmark_v5(
            resumen,
            db=db,
            user_id=1,
            activos_db=[],
            filas=[],
            current_fx=200,
        )
        self.assertIs(out, resumen)
        self.assertEqual(db.query_calls, 0)
        self.assertNotIn("portfolio_benchmark_v5", out)

    def test_enabled_attaches_cashflow_matched_ibc_benchmark(self):
        os.environ[FLAG_NAME] = "true"
        activo = SimpleNamespace(
            simbolo="AAA",
            creado_en=datetime(2026, 1, 2, 10, 0, 0),
        )
        tx = SimpleNamespace(
            id=1,
            usuario_id=7,
            simbolo="AAA",
            tipo="compra",
            cantidad=10,
            precio=100,
            comision=0,
            registro=0,
            iva=16,
            fecha=datetime(2026, 1, 2, 10, 0, 0),
            notas=None,
            motivo=None,
            tasa_bcv=100,
            score=None,
            fee_total=0,
            neto=1000,
        )
        db = _DB([tx])
        ibc = [
            {"date": "2026-01-02", "close": 1000},
            {"date": "2026-09-01", "close": 1200},
        ]
        ibc_meta = {
            "source": "database:ibc_history_v5",
            "count": 2,
            "official_points": 2,
        }

        with patch(
            "services.portfolio_benchmark_context_v5.load_persisted_ibc",
            return_value=(ibc, ibc_meta),
        ):
            out = attach_portfolio_benchmark_v5(
                {"total": 1500},
                db=db,
                user_id=7,
                activos_db=[activo],
                filas=[{"simb": "AAA", "cantidad": 10, "costo_total": 1000, "val_mkt": 1500}],
                current_fx=200,
            )

        bench = out["portfolio_benchmark_v5"]
        self.assertTrue(bench["available"])
        self.assertAlmostEqual(bench["portfolio_return_bs_pct"], 50.0)
        self.assertAlmostEqual(bench["ibc_return_bs_pct"], 20.0)
        self.assertEqual(bench["coverage_pct"], 100.0)
        self.assertEqual(bench["ibc_source"], "database:ibc_history_v5")
        self.assertEqual(bench["ibc_points"], 2)
        self.assertEqual(bench["ibc_official_points"], 2)


if __name__ == "__main__":
    unittest.main()
