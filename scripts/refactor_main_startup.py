"""One-shot deterministic codemod: extract legacy startup from main.py.

It refuses to edit when the expected source block is not present exactly. This
keeps the refactor auditable and avoids fuzzy/regex modifications of production
code.
"""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from services.email import email_recuperar_password, email_bienvenida\n"
NEW_IMPORT = "from app.startup import run_startup\n"

OLD_BLOCK = '''# ── Init DB al arrancar ────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    init_db()
    _migrar_db()
    _crear_admin_si_no_existe()
    # Arrancar worker de alertas en background
    asyncio.create_task(loop_alertas())
    # Registrar webhook de Telegram
    await registrar_webhook_telegram()


def _migrar_db():
    """Agrega columnas nuevas a tablas existentes sin borrar datos."""
    from sqlalchemy import text
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
                pass  # La columna ya existe, ignorar


def _crear_admin_si_no_existe():
    """Crea la cuenta admin en producción si no existe. Lee credenciales de variables de entorno."""
    import os
    from datetime import datetime, timedelta
    from services.auth import hash_password

    email    = os.environ.get("ADMIN_EMAIL", "")
    password = os.environ.get("ADMIN_PASSWORD", "")
    nombre   = os.environ.get("ADMIN_NOMBRE", "Admin")

    if not email or not password:
        return  # No configurado, saltar

    db = SessionLocal()
    try:
        from database import Usuario, Suscripcion
        if db.query(Usuario).filter(Usuario.email == email).first():
            return  # Ya existe

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
    except Exception as e:
        print(f"[startup] Error creando admin: {e}")
        db.rollback()
    finally:
        db.close()

'''

NEW_BLOCK = '''# ── Init DB al arrancar ────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    # `registrar_webhook_telegram` se resuelve al ejecutar startup, después de
    # que el módulo completo haya terminado de importarse.
    await run_startup(registrar_webhook_telegram)

'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_BLOCK in text and NEW_IMPORT in text:
        print("startup extraction already applied")
        return 0
    if OLD_BLOCK not in text:
        raise SystemExit("refactor aborted: exact legacy startup block not found")
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: import anchor not found")
    if NEW_IMPORT not in text:
        text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT, 1)
    text = text.replace(OLD_BLOCK, NEW_BLOCK, 1)
    PATH.write_text(text, encoding="utf-8")
    print("startup extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
