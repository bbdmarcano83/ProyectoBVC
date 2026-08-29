import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from database import get_db, Usuario, Suscripcion

ALGORITHM = "HS256"
TOKEN_EXPIRE = int(os.environ.get("TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7)))
TRIAL_DIAS = 14
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()

_secret = os.environ.get("SECRET_KEY", "").strip()
if APP_ENV in {"production", "prod"} and len(_secret) < 32:
    raise RuntimeError("SECRET_KEY es obligatoria en producción y debe tener al menos 32 caracteres")
# En desarrollo/instancia efímera se genera una clave por proceso; nunca se usa
# una clave pública/hardcodeada compartida.
SECRET_KEY = _secret if len(_secret) >= 32 else secrets.token_urlsafe(48)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres")
    return pwd_context.hash(password)


def verificar_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def crear_token(data: dict) -> str:
    now = datetime.now(timezone.utc)
    payload = data.copy()
    payload.update({
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=TOKEN_EXPIRE)).timestamp()),
        "iss": "caracasbull",
    })
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decodificar_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], issuer="caracasbull")
    except JWTError:
        return None


def crear_usuario(db: Session, nombre: str, email: str, password: str) -> Usuario:
    email_norm = email.lower().strip()
    if not email_norm or "@" not in email_norm:
        raise ValueError("Email inválido")
    if db.query(Usuario).filter(Usuario.email == email_norm).first():
        raise ValueError("El email ya está registrado")

    usuario = Usuario(
        nombre=nombre.strip()[:100],
        email=email_norm,
        password_hash=hash_password(password),
        activo=True,
    )
    db.add(usuario)
    db.flush()
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
    email_norm = email.lower().strip()
    usuario = db.query(Usuario).filter(Usuario.email == email_norm).first()
    if not usuario or not usuario.activo:
        return None
    if not verificar_password(password, usuario.password_hash):
        return None
    return usuario


def obtener_usuario_por_id(db: Session, usuario_id: int) -> Optional[Usuario]:
    return db.query(Usuario).filter(Usuario.id == usuario_id, Usuario.activo.is_(True)).first()


def suscripcion_activa(usuario: Usuario) -> bool:
    if not usuario or not usuario.activo or not usuario.suscripcion:
        return False
    if not usuario.suscripcion.activa:
        return False
    if usuario.suscripcion.fecha_vence and datetime.utcnow() > usuario.suscripcion.fecha_vence:
        return False
    return True


def dias_restantes(usuario: Usuario) -> int:
    if not usuario.suscripcion or not usuario.suscripcion.fecha_vence:
        return 0
    return max(0, (usuario.suscripcion.fecha_vence - datetime.utcnow()).days)


def get_plan(usuario: Usuario) -> str:
    if not usuario.suscripcion or not suscripcion_activa(usuario):
        return "ninguno"
    return usuario.suscripcion.plan or "trial"


def get_usuario_actual(request: Request, db: Session = Depends(get_db)) -> Optional[Usuario]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decodificar_token(token)
    if not payload:
        return None
    usuario_id = payload.get("sub")
    try:
        uid = int(usuario_id)
    except (TypeError, ValueError):
        return None
    return obtener_usuario_por_id(db, uid)


def require_usuario(request: Request, db: Session = Depends(get_db)) -> Usuario:
    usuario = get_usuario_actual(request, db)
    if not usuario:
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/login"})
    return usuario


def require_suscripcion(request: Request, db: Session = Depends(get_db)) -> Usuario:
    usuario = require_usuario(request, db)
    if not suscripcion_activa(usuario):
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, headers={"Location": "/suscripcion"})
    return usuario
