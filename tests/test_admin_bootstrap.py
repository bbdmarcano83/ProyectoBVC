import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, Usuario, Suscripcion
from services.admin_bootstrap import ensure_admin_account


class AdminBootstrapTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine)

    def test_creates_admin_and_pro_subscription(self):
        with self.Session() as db, patch.dict(os.environ, {
            "ADMIN_EMAIL": "Admin@Example.com ",
            "ADMIN_PASSWORD": "password-seguro",
            "ADMIN_NOMBRE": "Administrador",
        }, clear=False):
            state = ensure_admin_account(db)
            self.assertTrue(state["created"])
            user = db.query(Usuario).one()
            self.assertEqual(user.email, "admin@example.com")
            self.assertTrue(user.es_admin)
            self.assertTrue(user.activo)
            self.assertEqual(user.suscripcion.plan, "pro")
            self.assertTrue(user.suscripcion.activa)

    def test_existing_normal_user_is_elevated_without_duplication(self):
        with self.Session() as db:
            user = Usuario(
                nombre="Usuario",
                email="admin@example.com",
                password_hash="hash-existente",
                es_admin=False,
                activo=True,
            )
            db.add(user)
            db.flush()
            db.add(Suscripcion(usuario_id=user.id, plan="trial", activa=True))
            db.commit()

            with patch.dict(os.environ, {
                "ADMIN_EMAIL": "ADMIN@example.com",
                "ADMIN_PASSWORD": "password-seguro",
            }, clear=False):
                state = ensure_admin_account(db)
                self.assertFalse(state["created"])
                self.assertTrue(state["updated"])
                users = db.query(Usuario).all()
                self.assertEqual(len(users), 1)
                self.assertEqual(users[0].password_hash, "hash-existente")
                self.assertTrue(users[0].es_admin)
                self.assertEqual(users[0].suscripcion.plan, "pro")

    def test_second_run_is_idempotent(self):
        env = {
            "ADMIN_EMAIL": "admin@example.com",
            "ADMIN_PASSWORD": "password-seguro",
        }
        with self.Session() as db, patch.dict(os.environ, env, clear=False):
            first = ensure_admin_account(db)
            second = ensure_admin_account(db)
            self.assertTrue(first["created"])
            self.assertFalse(second["created"])
            self.assertFalse(second["updated"])
            self.assertEqual(db.query(Usuario).count(), 1)
            self.assertEqual(db.query(Suscripcion).count(), 1)


if __name__ == "__main__":
    unittest.main()
