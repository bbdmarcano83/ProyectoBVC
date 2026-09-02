"""Persistencia auditable del Índice Bursátil Caracas (IBC) para V5.

Cada fecha conserva nivel, URL y clasificación de fuente. Un punto existente sólo
se reemplaza si la nueva fuente tiene mayor prioridad/confianza o si pertenece a
la misma fuente y corrige el nivel.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from sqlalchemy import MetaData, Table, Column, Integer, Float, String, DateTime, UniqueConstraint, Index, select, insert, update
from sqlalchemy.sql import func

from database import engine, SessionLocal
from services.ibc_sources_v5 import classify_source

metadata = MetaData()
IBC_HISTORY_V5 = Table(
    "ibc_history_v5",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("rate_date", String(10), nullable=False),
    Column("close", Float, nullable=False),
    Column("source_url", String(700), nullable=False),
    Column("source_type", String(40), nullable=False),
    Column("source_confidence", Integer, nullable=False),
    Column("source_official", Integer, nullable=False, default=0),
    Column("fetched_at", DateTime, server_default=func.now(), nullable=False),
    Column("updated_at", DateTime, server_default=func.now(), nullable=False),
    UniqueConstraint("rate_date", name="uq_ibc_history_v5_date"),
    Index("ix_ibc_history_v5_date", "rate_date"),
)


def ensure_ibc_schema() -> None:
    IBC_HISTORY_V5.create(bind=engine, checkfirst=True)


def _normalize_date(raw) -> str | None:
    value = str(raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value[:10], fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _level(raw) -> float | None:
    try:
        if isinstance(raw, str):
            text = raw.strip()
            if "," in text:
                text = text.replace(".", "").replace(",", ".")
            return float(text)
        return float(raw)
    except (TypeError, ValueError):
        return None


def persist_ibc_points(points: Iterable[dict]) -> dict:
    """Upsert fail-closed de puntos IBC con fuente registrada."""
    ensure_ibc_schema()
    inserted = 0
    updated = 0
    rejected = 0
    unchanged = 0

    with SessionLocal() as db:
        for raw in points or []:
            if not isinstance(raw, dict):
                rejected += 1
                continue
            day = _normalize_date(raw.get("date") or raw.get("fecha") or raw.get("as_of"))
            close = _level(raw.get("close") or raw.get("cierre") or raw.get("value") or raw.get("nivel"))
            source_url = str(raw.get("source_url") or "").strip()
            source = classify_source(source_url)
            if not day or close is None or close <= 0 or source["confidence"] < 75:
                rejected += 1
                continue

            existing = db.execute(select(IBC_HISTORY_V5).where(IBC_HISTORY_V5.c.rate_date == day)).mappings().first()
            values = {
                "close": close,
                "source_url": source_url,
                "source_type": source["source_type"],
                "source_confidence": int(source["confidence"]),
                "source_official": 1 if source["official"] else 0,
                "updated_at": datetime.utcnow(),
            }
            if existing is None:
                db.execute(insert(IBC_HISTORY_V5).values(rate_date=day, **values))
                inserted += 1
                continue

            old_source = classify_source(existing.get("source_url", ""))
            better = source["priority"] < old_source["priority"]
            same_source = source["source_type"] == old_source["source_type"] and source_url == existing.get("source_url")
            changed_level = abs(float(existing["close"]) - close) > 1e-9
            if better or (same_source and changed_level):
                db.execute(update(IBC_HISTORY_V5).where(IBC_HISTORY_V5.c.id == existing["id"]).values(**values))
                updated += 1
            else:
                unchanged += 1
        db.commit()

    return {"inserted": inserted, "updated": updated, "rejected": rejected, "unchanged": unchanged}


def load_persisted_ibc() -> tuple[list[dict], dict]:
    ensure_ibc_schema()
    with SessionLocal() as db:
        rows = db.execute(select(IBC_HISTORY_V5).order_by(IBC_HISTORY_V5.c.rate_date.asc())).mappings().all()
    points = [
        {
            "date": r["rate_date"],
            "close": float(r["close"]),
            "source_url": r["source_url"],
            "source_type": r["source_type"],
            "source_confidence": int(r["source_confidence"]),
            "source_official": bool(r["source_official"]),
        }
        for r in rows
    ]
    return points, {
        "available": bool(points),
        "source": "database:ibc_history_v5",
        "count": len(points),
        "official_points": sum(1 for p in points if p["source_official"]),
        "audited_points": len(points),
    }
