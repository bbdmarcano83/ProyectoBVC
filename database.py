import os

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, DateTime, ForeignKey,
    Text, UniqueConstraint, CheckConstraint, Index, event,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func

# Sin DATABASE_URL externa, la app usa deliberadamente una SQLite EFÍMERA.
# No debe considerarse storage persistente ni respaldo.
RAW_DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


def _normalizar_database_url(url: str) -> str:
    """Normaliza URLs PostgreSQL para usar Psycopg 3 de forma explícita."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = _normalizar_database_url(RAW_DATABASE_URL) if RAW_DATABASE_URL else "sqlite:////tmp/caracasbull.db"
DB_PERSISTENCE_MODE = "external" if RAW_DATABASE_URL else "ephemeral"
IS_SQLITE = DATABASE_URL.startswith("sqlite")
IS_POSTGRES = DATABASE_URL.startswith("postgresql+") or DATABASE_URL.startswith("postgresql://")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    pool_pre_ping=True,
    pool_recycle=300 if IS_POSTGRES else -1,
)

if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    es_admin = Column(Boolean, default=False, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    creado_en = Column(DateTime, server_default=func.now())
    telegram_chat_id = Column(String(50), nullable=True)
    telegram_codigo = Column(String(10), nullable=True)
    broker = Column(String(50), nullable=True)
    token_recuperacion = Column(String(100), nullable=True)
    token_expira = Column(DateTime, nullable=True)

    suscripcion = relationship("Suscripcion", back_populates="usuario", uselist=False, cascade="all, delete-orphan")
    activos = relationship("ActivoPortafolio", back_populates="usuario", cascade="all, delete-orphan")
    watchlist = relationship("Watchlist", back_populates="usuario", cascade="all, delete-orphan")
    alertas = relationship("AlertaPrecio", back_populates="usuario", cascade="all, delete-orphan")


class Suscripcion(Base):
    __tablename__ = "suscripciones"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), unique=True, nullable=False)
    plan = Column(String(20), default="trial", nullable=False)
    activa = Column(Boolean, default=True, nullable=False)
    fecha_inicio = Column(DateTime, server_default=func.now())
    fecha_vence = Column(DateTime, nullable=True)
    pago_id = Column(String(200), nullable=True)
    pago_status = Column(String(50), nullable=True)
    monto_usd = Column(Float, nullable=True)

    usuario = relationship("Usuario", back_populates="suscripcion")
    __table_args__ = (CheckConstraint("plan IN ('trial','basico','intermedio','pro')", name="ck_suscripcion_plan"),)


class ActivoPortafolio(Base):
    __tablename__ = "activos_portafolio"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    simbolo = Column(String(20), nullable=False)
    cantidad = Column(Float, nullable=False)
    precio_promedio = Column(Float, nullable=False)
    comision = Column(Float, default=0, nullable=False)
    registro = Column(Float, default=0, nullable=False)
    iva = Column(Float, default=16, nullable=False)
    creado_en = Column(DateTime, server_default=func.now())
    actualizado_en = Column(DateTime, server_default=func.now(), onupdate=func.now())

    usuario = relationship("Usuario", back_populates="activos")
    __table_args__ = (
        UniqueConstraint("usuario_id", "simbolo", name="uq_portafolio_usuario_simbolo"),
        CheckConstraint("cantidad >= 0", name="ck_portafolio_cantidad"),
        CheckConstraint("precio_promedio >= 0", name="ck_portafolio_precio"),
    )


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    simbolo = Column(String(20), nullable=False)
    creado_en = Column(DateTime, server_default=func.now())

    usuario = relationship("Usuario", back_populates="watchlist")
    __table_args__ = (UniqueConstraint("usuario_id", "simbolo", name="uq_watchlist_usuario_simbolo"),)


class TransaccionHistorial(Base):
    __tablename__ = "transacciones"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    simbolo = Column(String(20), nullable=False)
    tipo = Column(String(10), nullable=False)
    cantidad = Column(Float, nullable=False)
    precio = Column(Float, nullable=False)
    comision = Column(Float, default=0)
    registro = Column(Float, default=0)
    iva = Column(Float, default=16)
    fecha = Column(DateTime, server_default=func.now())
    notas = Column(String(200), nullable=True)
    motivo = Column(String(50), nullable=True)
    tasa_bcv = Column(Float, nullable=True)
    score = Column(Integer, nullable=True)
    fee_total = Column(Float, nullable=True)
    neto = Column(Float, nullable=True)

    usuario = relationship("Usuario", backref="transacciones")
    __table_args__ = (
        CheckConstraint("tipo IN ('compra','venta')", name="ck_transaccion_tipo"),
        CheckConstraint("cantidad > 0", name="ck_transaccion_cantidad"),
        CheckConstraint("precio > 0", name="ck_transaccion_precio"),
        Index("ix_transaccion_usuario_fecha", "usuario_id", "fecha"),
    )


class PagoHistorial(Base):
    __tablename__ = "pagos_historial"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    nowpayments_id = Column(String(200), nullable=True, index=True)
    plan = Column(String(20))
    monto = Column(Float)
    moneda = Column(String(10), default="USDT")
    status = Column(String(50), index=True)
    creado_en = Column(DateTime, server_default=func.now())
    __table_args__ = (Index("ix_pago_usuario_fecha", "usuario_id", "creado_en"),)


class AlertaPrecio(Base):
    __tablename__ = "alertas_precio"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    simbolo = Column(String(20), nullable=False)
    tipo = Column(String(10), nullable=False)
    porcentaje = Column(Float, nullable=False)
    activa = Column(Boolean, default=True, nullable=False)
    disparada = Column(Boolean, default=False, nullable=False)
    creado_en = Column(DateTime, server_default=func.now())

    usuario = relationship("Usuario", back_populates="alertas")
    __table_args__ = (
        CheckConstraint("tipo IN ('subida','bajada')", name="ck_alerta_tipo"),
        CheckConstraint("porcentaje > 0", name="ck_alerta_porcentaje"),
    )


def init_db():
    Base.metadata.create_all(bind=engine)
    backend = "sqlite-ephemeral" if IS_SQLITE else ("postgresql-external" if IS_POSTGRES else "external")
    print(f"[DB] modo={DB_PERSISTENCE_MODE} backend={backend}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
