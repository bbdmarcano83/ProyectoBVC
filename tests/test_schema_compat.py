import unittest

from database import init_db, SessionLocal
from services.schema_compat import ensure_legacy_columns, REQUIRED_COLUMNS


class SchemaCompatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()

    def test_existing_schema_is_idempotent(self):
        with SessionLocal() as db:
            first = ensure_legacy_columns(db)
            second = ensure_legacy_columns(db)
        self.assertTrue(first["ok"], first)
        self.assertTrue(second["ok"], second)
        self.assertEqual(second["added"], [])
        self.assertIn(second["dialect"], {"sqlite", "postgresql"})

    def test_required_columns_are_explicit_internal_contract(self):
        self.assertIn("usuarios", REQUIRED_COLUMNS)
        self.assertIn("transacciones", REQUIRED_COLUMNS)
        self.assertEqual(REQUIRED_COLUMNS["usuarios"]["token_expira"], "TIMESTAMP")
        self.assertEqual(REQUIRED_COLUMNS["transacciones"]["fee_total"], "FLOAT")


if __name__ == "__main__":
    unittest.main()
