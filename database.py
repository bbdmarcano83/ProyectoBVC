from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func
import os

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./caracasbull.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── Modelos ───────────────────────────────────────────────────────────────────

class Usuario(Base):
    __tablename__ = "usuarios"

    id            = Column(Integer, primary_key=True, index=True)
    nombre        = Column(String(100), nullable=False)
    email         = Column(String(150), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    es_admin      = Column(Boolean, default=False)
    activo        = Column(Boolean, default=True)
    creado_en     = Column(DateTime, server_default=func.now())

    telegram_chat_id   = Column(String(50), nullable=True)
    telegram_codigo    = Column(String(10), nullable=True)
    broker             = Column(String(50), nullable=True)
    token_recuperacion = Column(String(100), nullable=True)
    token_expira       = Column(DateTime, nullable=True)

    suscripcion   = relationship("Suscripcion", back_populates="usuario", uselist=False)
    activos       = relationship("ActivoPortafolio", back_populates="usuario", cascade="all, delete-orphan")
    watchlist     = relationship("Watchlist", back_populates="usuario", cascade="all, delete-orphan")
    alertas       = relationship("AlertaPrecio", back_populates="usuario", cascade="all, delete-orphan")


class Suscripcion(Base):
    __tablename__ = "suscripciones"

    id              = Column(Integer, primary_key=True, index=True)
    usuario_id      = Column(Integer, ForeignKey("usuarios.id"), unique=True)
    plan            = Column(String(20), default="trial")   # trial | basico | pro
    activa          = Column(Boolean, default=True)
    fecha_inicio    = Column(DateTime, server_default=func.now())
    fecha_vence     = Column(DateTime, nullable=True)
    pago_id         = Column(String(200), nullable=True)    # ID de NOWPayments
    pago_status     = Column(String(50), nullable=True)     # waiting | confirming | confirmed | failed
    monto_usd       = Column(Float, nullable=True)

    usuario         = relationship("Usuario", back_populates="suscripcion")


class ActivoPortafolio(Base):
    __tablename__ = "activos_portafolio"

    id              = Column(Integer, primary_key=True, index=True)
    usuario_id      = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    simbolo         = Column(String(20), nullable=False)
    cantidad        = Column(Float, nullable=False)
    precio_promedio = Column(Float, nullable=False)
    comision        = Column(Float, default=0)
    registro        = Column(Float, default=0)
    iva             = Column(Float, default=16)
    creado_en       = Column(DateTime, server_default=func.now())
    actualizado_en  = Column(DateTime, server_default=func.now(), onupdate=func.now())

    usuario         = relationship("Usuario", back_populates="activos")


class Watchlist(Base):
    __tablename__ = "watchlist"

    id          = Column(Integer, primary_key=True, index=True)
    usuario_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    simbolo     = Column(String(20), nullable=False)
    creado_en   = Column(DateTime, server_default=func.now())

    usuario     = relationship("Usuario", back_populates="watchlist")


class TransaccionHistorial(Base):
    __tablename__ = "transacciones"

    id          = Column(Integer, primary_key=True, index=True)
    usuario_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    simbolo     = Column(String(20), nullable=False)
    tipo        = Column(String(10), nullable=False)   # "compra" | "venta"
    cantidad    = Column(Float, nullable=False)
    precio      = Column(Float, nullable=False)
    comision    = Column(Float, default=0)
    registro    = Column(Float, default=0)
    iva         = Column(Float, default=16)
    fecha       = Column(DateTime, server_default=func.now())
    notas       = Column(String(200), nullable=True)

    usuario     = relationship("Usuario", backref="transacciones")


class PagoHistorial(Base):
    __tablename__ = "pagos_historial"

    id              = Column(Integer, primary_key=True, index=True)
    usuario_id      = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    nowpayments_id  = Column(String(200), nullable=True)
    plan            = Column(String(20))
    monto           = Column(Float)
    moneda          = Column(String(10), default="USDT")
    status          = Column(String(50))
    creado_en       = Column(DateTime, server_default=func.now())


class AlertaPrecio(Base):
    __tablename__ = "alertas_precio"

    id          = Column(Integer, primary_key=True, index=True)
    usuario_id  = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    simbolo     = Column(String(20), nullable=False)
    tipo        = Column(String(10), nullable=False)   # "subida" | "bajada"
    porcentaje  = Column(Float, nullable=False)         # ej: 5.0 = 5%
    activa      = Column(Boolean, default=True)
    disparada   = Column(Boolean, default=False)
    creado_en   = Column(DateTime, server_default=func.now())

    usuario     = relationship("Usuario", back_populates="alertas")


# ── Inicialización ────────────────────────────────────────────────────────────

def init_db():
    """Crea todas las tablas si no existen."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Generador de sesión para usar como dependencia en FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
