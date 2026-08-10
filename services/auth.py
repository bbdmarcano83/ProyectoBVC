import os
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from database import get_db, Usuario, Suscripcion

# ── Configuración ─────────────────────────────────────────────────────────────
SECRET_KEY   = os.environ.get("SECRET_KEY", "caracasbull-dev-secret-cambiar-en-produccion")
ALGORITHM    = "HS256"
TOKEN_EXPIRE = 60 * 24 * 7  # 7 días en minutos

TRIAL_DIAS   = 14  # días de prueba gratuita

pwd_context  = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Contraseñas ───────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verificar_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────

def crear_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decodificar_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# ── Usuarios ──────────────────────────────────────────────────────────────────

def crear_usuario(db: Session, nombre: str, email: str, password: str) -> Usuario:
    """Crea un usuario nuevo con período de prueba de 14 días."""
    if db.query(Usuario).filter(Usuario.email == email).first():
        raise ValueError("El email ya está registrado")

    usuario = Usuario(
        nombre=nombre,
        email=email.lower().strip(),
        password_hash=hash_password(password),
    )
    db.add(usuario)
    db.flush()  # obtener el ID sin hacer commit todavía

    # Crear suscripción trial automáticamente
    suscripcion = Suscripcion(
        usuario_id=usuario.id,
        plan="trial",
        activa=True,
        fecha_inicio=datetime.utcnow(),
        fecha_vence=datetime.utcnow() + timedelta(days=TRIAL_DIAS),
    )
    db.add(suscripcion)
    db.commit()
    db.refresh(usuario)
    return usuario


def autenticar_usuario(db: Session, email: str, password: str) -> Optional[Usuario]:
    usuario = db.query(Usuario).filter(Usuario.email == email.lower().strip()).first()
    if not usuario or not verificar_password(password, usuario.password_hash):
        return None
    return usuario


def obtener_usuario_por_id(db: Session, usuario_id: int) -> Optional[Usuario]:
    return db.query(Usuario).filter(Usuario.id == usuario_id).first()


# ── Suscripción ───────────────────────────────────────────────────────────────

def suscripcion_activa(usuario: Usuario) -> bool:
    """Devuelve True si el usuario tiene suscripción vigente."""
    if not usuario.suscripcion:
        return False
    if not usuario.suscripcion.activa:
        return False
    if usuario.suscripcion.fecha_vence and datetime.utcnow() > usuario.suscripcion.fecha_vence:
        return False
    return True


def dias_restantes(usuario: Usuario) -> int:
    """Días que quedan en la suscripción actual."""
    if not usuario.suscripcion or not usuario.suscripcion.fecha_vence:
        return 0
    delta = usuario.suscripcion.fecha_vence - datetime.utcnow()
    return max(0, delta.days)


def get_plan(usuario: Usuario) -> str:
    """Devuelve el plan del usuario: 'trial', 'basico', 'intermedio', 'pro', o 'ninguno'."""
    if not usuario.suscripcion or not suscripcion_activa(usuario):
        return "ninguno"
    return usuario.suscripcion.plan or "trial"


# ── Dependencias FastAPI ──────────────────────────────────────────────────────

def get_usuario_actual(request: Request, db: Session = Depends(get_db)) -> Optional[Usuario]:
    """Lee el token de la cookie y devuelve el usuario actual o None."""
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decodificar_token(token)
    if not payload:
        return None
    usuario_id = payload.get("sub")
    if not usuario_id:
        return None
    return obtener_usuario_por_id(db, int(usuario_id))


def require_usuario(request: Request, db: Session = Depends(get_db)) -> Usuario:
    """Dependencia que exige usuario autenticado — redirige al login si no."""
    usuario = get_usuario_actual(request, db)
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )
    return usuario


def require_suscripcion(request: Request, db: Session = Depends(get_db)) -> Usuario:
    """Dependencia que exige usuario autenticado Y suscripción activa."""
    usuario = require_usuario(request, db)
    if not suscripcion_activa(usuario):
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/suscripcion"},
        )
    return usuario
