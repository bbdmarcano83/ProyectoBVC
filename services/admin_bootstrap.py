import os
from datetime import datetime, timedelta

from sqlalchemy.orm import Session


def ensure_admin_account(db: Session) -> dict:
    """Crea o asegura la cuenta Admin sin duplicarla.

    Antes del rol Admin ejecuta la compatibilidad de esquema dialect-safe para
    instalaciones legacy. Esto sustituye como fuente de verdad al bloque SQL
    antiguo de main.py, sin depender de que exista una cuenta Admin configurada.

    - Normaliza ADMIN_EMAIL igual que el login.
    - Si el usuario ya existe, conserva su password y sus datos normales.
    - Garantiza es_admin=True, activo=True y plan pro activo.
    - No hace cambios de cuenta si faltan ADMIN_EMAIL o ADMIN_PASSWORD.
    """
    from database import Usuario, Suscripcion
    from services.auth import hash_password
    from services.schema_compat import ensure_legacy_columns

    schema_state = ensure_legacy_columns(db)

    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    nombre = os.environ.get("ADMIN_NOMBRE", "Admin").strip()[:100] or "Admin"

    if not email or not password:
        return {
            "configured": False,
            "created": False,
            "updated": False,
            "schema_compat": schema_state,
        }

    if "@" not in email:
        raise ValueError("ADMIN_EMAIL inválido")
    if len(password) < 8:
        raise ValueError("ADMIN_PASSWORD debe tener al menos 8 caracteres")

    usuario = db.query(Usuario).filter(Usuario.email == email).first()
    created = False
    updated = False

    if usuario is None:
        usuario = Usuario(
            nombre=nombre,
            email=email,
            password_hash=hash_password(password),
            es_admin=True,
            activo=True,
        )
        db.add(usuario)
        db.flush()
        created = True
    else:
        # El Admin también es un usuario normal: no se reemplaza su cuenta ni
        # se borran portfolio/watchlist/transacciones. Solo se asegura su rol.
        if not usuario.es_admin:
            usuario.es_admin = True
            updated = True
        if not usuario.activo:
            usuario.activo = True
            updated = True

    suscripcion = db.query(Suscripcion).filter(Suscripcion.usuario_id == usuario.id).first()
    vence_admin = datetime.utcnow() + timedelta(days=365 * 100)

    if suscripcion is None:
        suscripcion = Suscripcion(
            usuario_id=usuario.id,
            plan="pro",
            activa=True,
            fecha_inicio=datetime.utcnow(),
            fecha_vence=vence_admin,
        )
        db.add(suscripcion)
        updated = True
    else:
        if suscripcion.plan != "pro":
            suscripcion.plan = "pro"
            updated = True
        if not suscripcion.activa:
            suscripcion.activa = True
            updated = True
        if suscripcion.fecha_vence is None or suscripcion.fecha_vence < datetime.utcnow() + timedelta(days=365 * 10):
            suscripcion.fecha_vence = vence_admin
            updated = True

    db.commit()
    db.refresh(usuario)
    return {
        "configured": True,
        "created": created,
        "updated": updated,
        "user_id": usuario.id,
        "email": usuario.email,
        "is_admin": bool(usuario.es_admin),
        "plan": suscripcion.plan,
        "schema_compat": schema_state,
    }
