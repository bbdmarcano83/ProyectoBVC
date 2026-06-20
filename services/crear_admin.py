"""
Ejecutar UNA sola vez para crear la cuenta de administrador.
    py -3.12 crear_admin.py
"""
from datetime import datetime, timedelta
from database import init_db, SessionLocal, Usuario, Suscripcion
from services.auth import hash_password

# ── Configura tus datos aquí ──────────────────────────────────────────────────
NOMBRE   = "CEO"
EMAIL    = "admin@caracasbull.com"   # cambia por tu email real
PASSWORD = "admin1234"               # cambia por una contraseña segura
# ─────────────────────────────────────────────────────────────────────────────

def crear_admin():
    init_db()
    db = SessionLocal()

    existente = db.query(Usuario).filter(Usuario.email == EMAIL).first()
    if existente:
        print(f"⚠  Ya existe una cuenta con {EMAIL}")
        db.close()
        return

    usuario = Usuario(
        nombre=NOMBRE,
        email=EMAIL,
        password_hash=hash_password(PASSWORD),
        es_admin=True,
        activo=True,
    )
    db.add(usuario)
    db.flush()

    # Suscripción vitalicia (100 años)
    suscripcion = Suscripcion(
        usuario_id=usuario.id,
        plan="pro",
        activa=True,
        fecha_inicio=datetime.utcnow(),
        fecha_vence=datetime.utcnow() + timedelta(days=365 * 100),
    )
    db.add(suscripcion)
    db.commit()

    print(f"✓ Admin creado correctamente")
    print(f"  Email:      {EMAIL}")
    print(f"  Contraseña: {PASSWORD}")
    print(f"  Plan:       Pro (vitalicio)")
    print(f"\nYa puedes iniciar sesión en localhost:8000/login")
    db.close()

if __name__ == "__main__":
    crear_admin()
