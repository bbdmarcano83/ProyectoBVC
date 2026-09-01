"""Histórico USD/VES para normalización fundamental V5.

Fuente primaria operativa: DolarAPI, que declara datos derivados del BCV. Para
períodos anteriores a su cobertura se permite un fallback anual secundario sólo
cuando dos proveedores históricos independientes coinciden. La procedencia nunca
se presenta como BCV oficial y queda explícita en metadata.

Reglas:
- tasa de cierre = última tasa publicada <= fecha del estado;
- promedio de período = promedio calendario con forward-fill cuando hay historia diaria completa;
- fallback anual sólo para FY completo y años explícitamente verificados;
- nunca se usa la tasa actual para un estado histórico;
- los datos primarios se cachean/persisten en la misma DB (Neon en producción).
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

FALLBACK_SOURCE_URLS = (
    "https://www.exchange-rates.org/exchange-rate-history/usd-ves-{year}",
    "https://www.valutafx.com/history/usd-ves-{year}",
)
FALLBACK_SOURCE_NAME = "Exchange-Rates.org + ValutaFX · USD/VES historical cross-check"
FALLBACK_SOURCE_KIND = "crosschecked_secondary_history"
FALLBACK_SOURCE_CONFIDENCE = 80

# Valores anuales aceptados únicamente después de coincidencia exacta entre los
# dos proveedores indicados arriba. close = último cierre publicado del año.
# average = promedio anual publicado por ambas fuentes.
VERIFIED_ANNUAL_FX_FALLBACK = {
    2022: {"close": 17.489, "average": 6.7632, "close_date": "2022-12-30"},
    2023: {"close": 35.959, "average": 28.780, "close_date": "2023-12-29"},
}


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


def calendar_average_from_records(records: list[tuple[date, float]], start: str | date | datetime,
                                  end: str | date | datetime) -> float | None:
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


def get_period_average(start: str | date | datetime, end: str | date | datetime,
                       refresh_if_missing: bool = True) -> float | None:
    records = _load_records()
    avg = calendar_average_from_records(records, start, end)
    if avg is None and refresh_if_missing:
        refresh_history()
        avg = calendar_average_from_records(_load_records(), start, end)
    return avg


def infer_period_start(fiscal_period: str | None, as_of: str) -> str | None:
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


def _full_year_fallback(start: str | None, end: str, fiscal_period: str | None) -> dict | None:
    if not start:
        return None
    try:
        s, e = _date(start), _date(end)
    except (TypeError, ValueError):
        return None
    fp = str(fiscal_period or "").upper().strip()
    is_annual = fp.startswith("FY") or fp in {str(e.year), f"ANUAL-{e.year}"}
    if not is_annual or s != date(e.year, 1, 1) or e != date(e.year, 12, 31):
        return None
    return VERIFIED_ANNUAL_FX_FALLBACK.get(e.year)


def attach_historical_bcv_fx(data: dict, *, as_of: str, fiscal_period: str | None = None,
                             period_start: str | None = None, refresh_if_missing: bool = True) -> tuple[dict, dict]:
    """Añade FX histórico manteniendo trazabilidad primaria/fallback por componente."""
    out = dict(data or {})
    currency = str(out.get("currency") or "").upper().strip()
    basis = str(out.get("monetary_basis") or "nominal_ves").lower().strip()
    if currency in {"USD", "US$"}:
        return out, {"ok": True, "skipped": True, "reason": "reported_usd"}
    if currency not in {"VES", "BS", "BS."}:
        return out, {"ok": False, "error": "unsupported_or_missing_currency"}

    start = period_start or infer_period_start(fiscal_period, as_of)
    close_rate = get_close_rate(as_of, refresh_if_missing=refresh_if_missing)
    avg_rate = get_period_average(start, as_of, refresh_if_missing=refresh_if_missing) if basis == "nominal_ves" and start else None

    fallback = _full_year_fallback(start, as_of, fiscal_period)
    fallback_used = []
    if fallback:
        if close_rate is None:
            close_rate = float(fallback["close"])
            fallback_used.append("close")
        if basis == "nominal_ves" and avg_rate is None:
            avg_rate = float(fallback["average"])
            fallback_used.append("average")

    if close_rate is not None:
        out["fx_rate_bcv_close"] = close_rate
    if avg_rate is not None:
        out["fx_rate_bcv_avg"] = avg_rate

    if fallback_used:
        year = _date(as_of).year
        fallback_urls = [u.format(year=year) for u in FALLBACK_SOURCE_URLS]
        source_kind = FALLBACK_SOURCE_KIND
        source_confidence = FALLBACK_SOURCE_CONFIDENCE
        source_name = FALLBACK_SOURCE_NAME
        source_url = fallback_urls[0]
        origin = "USD/VES historical cross-check"
        out["fx_fallback_components"] = fallback_used
        out["fx_fallback_sources"] = fallback_urls
        out["fx_primary_source_url"] = HISTORY_URL
    else:
        source_kind = SOURCE_KIND
        source_confidence = SOURCE_CONFIDENCE
        source_name = SOURCE_NAME
        source_url = HISTORY_URL
        origin = "BCV-derived"

    out["fx_source_url"] = source_url
    out["fx_source_name"] = source_name
    out["fx_source_kind"] = source_kind
    out["fx_source_confidence"] = source_confidence
    out["fx_origin"] = origin
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
        "source_url": source_url,
        "source_kind": source_kind,
        "source_confidence": source_confidence,
        "fallback_components": fallback_used,
        "fallback_sources": out.get("fx_fallback_sources", []),
        "primary_source_url": HISTORY_URL,
    }
