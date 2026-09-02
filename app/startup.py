"""Application startup/runtime extracted from legacy ``main.py``.

This module intentionally preserves the legacy startup behavior during the
structural refactor. Functional cleanup of migrations/admin bootstrap is a
separate change and must not be mixed with route-preserving modularization.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from typing import Awaitable, Callable

from sqlalchemy import text

from database import SessionLocal, init_db
from services.alertas_worker import loop_alertas
from services.auth import hash_password


WebHookRegistrar = Callable[[], Awaitable[object]]


def migrate_legacy_schema() -> None:
    """Agrega columnas nuevas a tablas existentes sin borrar datos.

    Kept byte-for-byte equivalent in SQL/exception policy to the legacy helper
    while routes are being modularized.
    """
    migraciones = [
        "ALTER TABLE usuarios ADD COLUMN telegram_chat_id VARCHAR(50)",
        "ALTER TABLE usuarios ADD COLUMN telegram_codigo VARCHAR(10)",
        "ALTER TABLE usuarios ADD COLUMN broker VARCHAR(50)",
        "ALTER TABLE usuarios ADD COLUMN token_recuperacion VARCHAR(100)",
        "ALTER TABLE usuarios ADD COLUMN token_expira DATETIME",
        """CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id),
            simbolo VARCHAR(20),
            tipo VARCHAR(10),
            cantidad FLOAT,
            precio FLOAT,
            comision FLOAT DEFAULT 0,
            registro FLOAT DEFAULT 0,
            iva FLOAT DEFAULT 16,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
            notas VARCHAR(200)
        )""",
        "ALTER TABLE transacciones ADD COLUMN motivo VARCHAR(50)",
        "ALTER TABLE transacciones ADD COLUMN tasa_bcv FLOAT",
        "ALTER TABLE transacciones ADD COLUMN score INTEGER",
        "ALTER TABLE transacciones ADD COLUMN fee_total FLOAT",
        "ALTER TABLE transacciones ADD COLUMN neto FLOAT",
    ]
    with SessionLocal() as db:
        for sql in migraciones:
            try:
                db.execute(text(sql))
                db.commit()
                print(f"[Migración] OK: {sql}")
            except Exception:
                pass


def create_legacy_admin_if_missing() -> None:
    """Preserve the exact legacy admin creation path during refactor."""
    email = os.environ.get("ADMIN_EMAIL", "")
    password = os.environ.get("ADMIN_PASSWORD", "")
    nombre = os.environ.get("ADMIN_NOMBRE", "Admin")

    if not email or not password:
        return

    db = SessionLocal()
    try:
        from database import Suscripcion, Usuario

        if db.query(Usuario).filter(Usuario.email == email).first():
            return

        usuario = Usuario(
            nombre=nombre,
            email=email,
            password_hash=hash_password(password),
            es_admin=True,
            activo=True,
        )
        db.add(usuario)
        db.flush()

        suscripcion = Suscripcion(
            usuario_id=usuario.id,
            plan="pro",
            activa=True,
            fecha_inicio=datetime.utcnow(),
            fecha_vence=datetime.utcnow() + timedelta(days=365 * 100),
        )
        db.add(suscripcion)
        db.commit()
        print(f"[startup] Admin creado: {email}")
    except Exception as exc:
        print(f"[startup] Error creando admin: {exc}")
        db.rollback()
    finally:
        db.close()


async def run_startup(register_telegram_webhook: WebHookRegistrar) -> None:
    """Run the same startup sequence formerly embedded in ``main.py``."""
    init_db()
    migrate_legacy_schema()
    create_legacy_admin_if_missing()
    asyncio.create_task(loop_alertas())
    await register_telegram_webhook()
