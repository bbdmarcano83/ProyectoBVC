"""Snapshots diarios de cartera para comparar Caracas Bull vs IBC sin sesgo retrospectivo.

La tabla se crea de forma aislada mediante SQLAlchemy Core para no tocar modelos
legacy. Cada usuario tiene como máximo un snapshot por día; nuevas corridas del
mismo día actualizan el registro existente.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Mapping, Any

from sqlalchemy import (
    MetaData, Table, Column, Integer, Float, String, Date, DateTime,
    UniqueConstraint, Index, select, insert, update,
)
from sqlalchemy.sql import func

from database import engine, SessionLocal, ActivoPortafolio

metadata = MetaData()
PORTFOLIO_SNAPSHOTS_V5 = Table(
    "portfolio_snapshots_v5",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("usuario_id", Integer, nullable=False),
    Column("as_of", Date, nullable=False),
    Column("total_cost_bs", Float, nullable=False, default=0.0),
    Column("total_market_bs", Float, nullable=False, default=0.0),
    Column("total_market_usd", Float, nullable=True),
    Column("fx_bcv", Float, nullable=True),
    Column("ibc_level", Float, nullable=True),
    Column("positions_count", Integer, nullable=False, default=0),
    Column("source", String(60), nullable=False, default="market_close"),
    Column("created_at", DateTime, server_default=func.now(), nullable=False),
    Column("updated_at", DateTime, server_default=func.now(), nullable=False),
    UniqueConstraint("usuario_id", "as_of", name="uq_portfolio_snapshot_v5_user_day"),
    Index("ix_portfolio_snapshot_v5_user_day", "usuario_id", "as_of"),
)


def ensure_snapshot_table() -> None:
    PORTFOLIO_SNAPSHOTS_V5.create(bind=engine, checkfirst=True)


def _f(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _day(value: date | datetime | str | None = None) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    return date.today()


def save_daily_snapshot(
    usuario_id: int,
    *,
    prices: Mapping[str, float],
    fx_bcv: float | None,
    ibc_level: float | None,
    as_of: date | datetime | str | None = None,
    source: str = "market_close",
) -> dict:
    """Calcula y persiste un snapshot diario idempotente de la cartera abierta."""
    ensure_snapshot_table()
    day = _day(as_of)
    with SessionLocal() as db:
        activos = db.query(ActivoPortafolio).filter(ActivoPortafolio.usuario_id == int(usuario_id)).all()
        total_cost = 0.0
        total_market = 0.0
        for a in activos:
            qty = max(0.0, _f(a.cantidad))
            prom = max(0.0, _f(a.precio_promedio))
            com = max(0.0, _f(a.comision))
            reg = max(0.0, _f(a.registro))
            iva = max(0.0, _f(a.iva))
            total_cost += qty * prom + com + reg + com * iva / 100.0
            px = _f(prices.get(str(a.simbolo).upper())) or prom
            total_market += qty * px

        fx = _f(fx_bcv)
        ibc = _f(ibc_level)
        market_usd = total_market / fx if fx > 0 else None
        values = {
            "total_cost_bs": total_cost,
            "total_market_bs": total_market,
            "total_market_usd": market_usd,
            "fx_bcv": fx if fx > 0 else None,
            "ibc_level": ibc if ibc > 0 else None,
            "positions_count": len(activos),
            "source": str(source or "market_close")[:60],
            "updated_at": datetime.utcnow(),
        }
        existing = db.execute(
            select(PORTFOLIO_SNAPSHOTS_V5.c.id).where(
                PORTFOLIO_SNAPSHOTS_V5.c.usuario_id == int(usuario_id),
                PORTFOLIO_SNAPSHOTS_V5.c.as_of == day,
            )
        ).first()
        if existing:
            db.execute(
                update(PORTFOLIO_SNAPSHOTS_V5)
                .where(PORTFOLIO_SNAPSHOTS_V5.c.id == existing.id)
                .values(**values)
            )
            saved = "updated"
        else:
            db.execute(insert(PORTFOLIO_SNAPSHOTS_V5).values(usuario_id=int(usuario_id), as_of=day, **values))
            saved = "created"
        db.commit()
        return {
            "saved": True,
            "action": saved,
            "as_of": day.isoformat(),
            "positions_count": len(activos),
            "total_cost_bs": round(total_cost, 2),
            "total_market_bs": round(total_market, 2),
            "total_market_usd": round(market_usd, 4) if market_usd is not None else None,
            "fx_bcv": fx if fx > 0 else None,
            "ibc_level": ibc if ibc > 0 else None,
        }


def load_snapshots(usuario_id: int) -> list[dict]:
    ensure_snapshot_table()
    with SessionLocal() as db:
        rows = db.execute(
            select(PORTFOLIO_SNAPSHOTS_V5)
            .where(PORTFOLIO_SNAPSHOTS_V5.c.usuario_id == int(usuario_id))
            .order_by(PORTFOLIO_SNAPSHOTS_V5.c.as_of.asc())
        ).mappings().all()
    return [dict(r) for r in rows]
