"""Histórico USD/VES para normalización fundamental V5.

Fuente operativa inicial: endpoint histórico de dólar oficial de DolarAPI, que
reporta datos derivados del BCV. No se presenta como portal oficial del BCV:
la procedencia queda explícita en cada registro y puede sustituirse por un
adaptador oficial en el futuro sin cambiar el contrato del motor.

Reglas:
- tasa de cierre = última tasa publicada <= fecha del estado;
- promedio de período = promedio calendario con forward-fill de la última tasa
  publicada, para no sesgar fines de semana/feriados;
- nunca se usa la tasa actual para un estado histórico;
- los datos se cachean/persisten en la misma DB (Neon en producción).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

import httpx
from sqlalchemy import Column, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from database import Base, SessionLocal, engine

HISTORY_URL = "https://ve.dolarapi.com/v1/historicos/dolares/oficial"
SOURCE_NAME = "DolarAPI · dólar oficial (fuente declarada: BCV)"
SOURCE_KIND = "bcv_derived_api"
SOURCE_CONFIDENCE = 95


class FxRateV5(Base):
    __tablename__ = "fx_rates_v5"

    id = Column(Integer, primary_key=True, index=True)
    rate_date = Column(String(10), nullable=False, index=True)
    currency_pair = Column(String(12), nullable=False, default="USD/VES")
    rate = Column(Float, nullable=False)
    source_name = Column(String(120), nullable=False)
    source_url = Column(String(500), nullable=False)
    source_kind = Column(String(40), nullable=False)
    source_confidence = Column(Integer, nullable=False, default=0)
    fetched_at = Column(DateTime, server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("rate_date", "currency_pair", name="uq_fx_v5_date_pair"),
    )


def ensure_fx_schema() -> None:
    FxRateV5.__table__.create(bind=engine, checkfirst=True)


def _date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def parse_official_history(payload: object) -> list[tuple[date, float]]:
    """Normaliza respuesta histórica; descarta registros inválidos/duplicados."""
    if not isinstance(payload, list):
        return []
    by_date: dict[date, float] = {}
    for row in payload:
        if not isinstance(row, dict):
            continue
        try:
            day = _date(str(row.get("fecha") or ""))
            rate = float(row.get("promedio") or row.get("venta") or row.get("compra") or 0)
        except (TypeError, ValueError):
            continue
        if rate <= 0:
            continue
        by_date[day] = rate
    return sorted(by_date.items(), key=lambda x: x[0])


def persist_rates(records: Iterable[tuple[date, float]]) -> int:
    """Upsert conservador: inserta fechas nuevas; actualiza sólo si cambió la tasa."""
    ensure_fx_schema()
    changed = 0
    with SessionLocal() as db:
        for day, rate in records:
            key = day.isoformat()
            row = db.query(FxRateV5).filter(
                FxRateV5.rate_date == key,
                FxRateV5.currency_pair == "USD/VES",
            ).first()
            if row is None:
                db.add(FxRateV5(
                    rate_date=key,
                    currency_pair="USD/VES",
                    rate=float(rate),
                    source_name=SOURCE_NAME,
                    source_url=HISTORY_URL,
                    source_kind=SOURCE_KIND,
                    source_confidence=SOURCE_CONFIDENCE,
                ))
                changed += 1
            elif abs(float(row.rate) - float(rate)) > 1e-9:
                row.rate = float(rate)
                row.source_name = SOURCE_NAME
                row.source_url = HISTORY_URL
                row.source_kind = SOURCE_KIND
                row.source_confidence = SOURCE_CONFIDENCE
                changed += 1
        db.commit()
    return changed


def refresh_history(timeout: float = 15.0) -> dict:
    """Descarga el histórico completo del endpoint oficial-BCV derivado."""
    try:
        response = httpx.get(
            HISTORY_URL,
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "CaracasBull-FXAudit/1.0"},
        )
        response.raise_for_status()
        records = parse_official_history(response.json())
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__, "count": 0, "changed": 0}
    if not records:
        return {"ok": False, "error": "empty_or_invalid_history", "count": 0, "changed": 0}
    changed = persist_rates(records)
    return {
        "ok": True,
        "count": len(records),
        "changed": changed,
        "first_date": records[0][0].isoformat(),
        "last_date": records[-1][0].isoformat(),
        "source": SOURCE_NAME,
        "source_url": HISTORY_URL,
        "source_kind": SOURCE_KIND,
        "source_confidence": SOURCE_CONFIDENCE,
    }


def _load_records() -> list[tuple[date, float]]:
    ensure_fx_schema()
    with SessionLocal() as db:
        rows = db.query(FxRateV5).filter(FxRateV5.currency_pair == "USD/VES").order_by(
            FxRateV5.rate_date.asc()
        ).all()
        out: list[tuple[date, float]] = []
        for row in rows:
            try:
                out.append((_date(row.rate_date), float(row.rate)))
            except (TypeError, ValueError):
                continue
        return out


def close_rate_from_records(records: list[tuple[date, float]], target: str | date | datetime) -> float | None:
    target_day = _date(target)
    eligible = [rate for day, rate in records if day <= target_day]
    return eligible[-1] if eligible else None


def calendar_average_from_records(
    records: list[tuple[date, float]],
    start: str | date | datetime,
    end: str | date | datetime,
) -> float | None:
    """Promedio calendario, usando la última tasa conocida para días sin publicación."""
    start_day, end_day = _date(start), _date(end)
    if end_day < start_day:
        return None
    ordered = sorted(records, key=lambda x: x[0])
    current = close_rate_from_records(ordered, start_day)
    if current is None:
        return None
    index = 0
    while index < len(ordered) and ordered[index][0] <= start_day:
        index += 1
    values: list[float] = []
    day = start_day
    while day <= end_day:
        while index < len(ordered) and ordered[index][0] <= day:
            current = ordered[index][1]
            index += 1
        values.append(float(current))
        day += timedelta(days=1)
    return round(sum(values) / len(values), 8) if values else None


def get_close_rate(target: str | date | datetime, refresh_if_missing: bool = True) -> float | None:
    records = _load_records()
    rate = close_rate_from_records(records, target)
    if rate is None and refresh_if_missing:
        refresh_history()
        rate = close_rate_from_records(_load_records(), target)
    return rate


def get_period_average(
    start: str | date | datetime,
    end: str | date | datetime,
    refresh_if_missing: bool = True,
) -> float | None:
    records = _load_records()
    avg = calendar_average_from_records(records, start, end)
    if avg is None and refresh_if_missing:
        refresh_history()
        avg = calendar_average_from_records(_load_records(), start, end)
    return avg


def infer_period_start(fiscal_period: str | None, as_of: str) -> str | None:
    """Infiere inicio para FY/H1/H2/Q1..Q4; si no es inequívoco, devuelve None."""
    fp = str(fiscal_period or "").upper().strip()
    end = _date(as_of)
    year = end.year
    if fp.startswith("FY") or fp in {str(year), f"ANUAL-{year}"}:
        return f"{year}-01-01"
    if "Q1" in fp:
        return f"{year}-01-01"
    if "Q2" in fp:
        return f"{year}-04-01"
    if "Q3" in fp:
        return f"{year}-07-01"
    if "Q4" in fp:
        return f"{year}-10-01"
    if "H1" in fp or "1S" in fp:
        return f"{year}-01-01"
    if "H2" in fp or "2S" in fp:
        return f"{year}-07-01"
    return None


def attach_historical_bcv_fx(data: dict, *, as_of: str, fiscal_period: str | None = None,
                             period_start: str | None = None, refresh_if_missing: bool = True) -> tuple[dict, dict]:
    """Añade metadatos FX históricos sin modificar las cifras originales."""
    out = dict(data or {})
    currency = str(out.get("currency") or "").upper().strip()
    basis = str(out.get("monetary_basis") or "nominal_ves").lower().strip()
    if currency in {"USD", "US$"}:
        return out, {"ok": True, "skipped": True, "reason": "reported_usd"}
    if currency not in {"VES", "BS", "BS."}:
        return out, {"ok": False, "error": "unsupported_or_missing_currency"}

    close_rate = get_close_rate(as_of, refresh_if_missing=refresh_if_missing)
    start = period_start or infer_period_start(fiscal_period, as_of)
    avg_rate = None
    if basis == "nominal_ves" and start:
        avg_rate = get_period_average(start, as_of, refresh_if_missing=refresh_if_missing)

    if close_rate is not None:
        out["fx_rate_bcv_close"] = close_rate
    if avg_rate is not None:
        out["fx_rate_bcv_avg"] = avg_rate
    out["fx_source_url"] = HISTORY_URL
    out["fx_source_name"] = SOURCE_NAME
    out["fx_source_kind"] = SOURCE_KIND
    out["fx_source_confidence"] = SOURCE_CONFIDENCE
    out["fx_origin"] = "BCV"
    out["fx_as_of"] = str(as_of)[:10]
    if start:
        out["fx_period_start"] = str(start)[:10]
    out["fx_period_end"] = str(as_of)[:10]

    ok = close_rate is not None and (basis != "nominal_ves" or avg_rate is not None)
    return out, {
        "ok": ok,
        "close_rate": close_rate,
        "average_rate": avg_rate,
        "period_start": start,
        "period_end": str(as_of)[:10],
        "source_url": HISTORY_URL,
        "source_kind": SOURCE_KIND,
        "source_confidence": SOURCE_CONFIDENCE,
    }
