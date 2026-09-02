"""Series históricas fundamentales comparables para Caracas Bull V5.

Construye series únicamente con snapshots validados y períodos anuales
comparables. No mezcla Q1/Q2/H1 con FY para calcular CAGR o consistencia.
Las cifras VES crudas nunca entran en una serie intertemporal: se exige campo
`*_usd` o que el documento haya sido reportado originalmente en USD.
"""
from __future__ import annotations

import json
from typing import Any

from database import SessionLocal, FundamentalDocument, FundamentalSnapshot

SERIES_FIELDS = {
    "net_income": "earnings_history_usd",
    "revenue": "revenue_history_usd",
    "free_cash_flow": "fcf_history_usd",
    "nav": "nav_history_usd",
    "equity": "equity_history_usd",
    "total_assets": "assets_history_usd",
}


def _f(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_annual_period(fiscal_period: str | None, document_type: str | None) -> bool:
    fp = str(fiscal_period or "").upper().strip()
    dt = str(document_type or "").lower().strip()
    if fp.startswith("FY"):
        return True
    if fp.isdigit() and len(fp) == 4:
        return True
    return any(token in dt for token in ("annual", "anual")) and not any(
        token in dt for token in ("quarter", "trimes", "semiannual", "semes")
    )


def _comparable_usd(data: dict, field: str) -> float | None:
    usd = _f(data.get(f"{field}_usd"))
    if usd is not None:
        return usd
    if str(data.get("currency") or "").upper().strip() in {"USD", "US$"}:
        return _f(data.get(field))
    return None


def _has_any_comparable_usd(data: dict) -> bool:
    return any(_comparable_usd(data, field) is not None for field in SERIES_FIELDS)


def build_series_from_records(records: list[dict]) -> dict:
    """Pure builder used by DB adapter and tests.

    Each record requires `as_of`, `fiscal_period`, `document_type`, `data`.
    Duplicate annual dates keep the record with highest validation score and,
    on tie, the latest snapshot id. A period counts toward USD history only if
    at least one supported monetary field is genuinely comparable in USD.
    """
    annual: dict[str, dict] = {}
    for record in records or []:
        if not _is_annual_period(record.get("fiscal_period"), record.get("document_type")):
            continue
        data = record.get("data")
        if not isinstance(data, dict):
            continue
        as_of = str(record.get("as_of") or data.get("as_of") or "")[:10]
        if not as_of:
            continue
        rank = (float(record.get("validation_score") or 0), int(record.get("snapshot_id") or 0))
        current = annual.get(as_of)
        if current is None or rank > current["rank"]:
            annual[as_of] = {"rank": rank, "data": data}

    dates = [day for day in sorted(annual) if _has_any_comparable_usd(annual[day]["data"])]
    result: dict[str, Any] = {
        "history_dates_usd": dates,
        "history_periods_usd": len(dates),
        "history_basis_v5": "annual_comparable_usd_only",
    }
    for field, output_key in SERIES_FIELDS.items():
        values: list[float] = []
        value_dates: list[str] = []
        for day in dates:
            value = _comparable_usd(annual[day]["data"], field)
            if value is None:
                continue
            values.append(value)
            value_dates.append(day)
        if values:
            result[output_key] = values
            result[f"{output_key}_dates"] = value_dates
    return result


def load_comparable_histories() -> dict[str, dict]:
    """Read validated snapshots + their document period metadata from SQL/Neon."""
    with SessionLocal() as db:
        rows = db.query(FundamentalSnapshot, FundamentalDocument).join(
            FundamentalDocument,
            FundamentalDocument.id == FundamentalSnapshot.document_id,
        ).filter(
            FundamentalSnapshot.validated.is_(True)
        ).order_by(
            FundamentalSnapshot.simbolo.asc(),
            FundamentalSnapshot.as_of.asc(),
            FundamentalSnapshot.id.asc(),
        ).all()

    grouped: dict[str, list[dict]] = {}
    for snap, doc in rows:
        try:
            data = json.loads(snap.data_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        grouped.setdefault(str(snap.simbolo).upper(), []).append({
            "as_of": snap.as_of,
            "fiscal_period": doc.fiscal_period,
            "document_type": doc.document_type,
            "validation_score": snap.validation_score,
            "snapshot_id": snap.id,
            "data": data,
        })

    return {symbol: build_series_from_records(records) for symbol, records in grouped.items()}


def attach_histories_to_latest(payload: dict[str, dict]) -> tuple[dict[str, dict], dict]:
    """Attach annual USD histories to latest snapshots without mutating DB rows."""
    histories = load_comparable_histories()
    out: dict[str, dict] = {}
    attached = 0
    with_two_or_more = 0
    for symbol, latest in (payload or {}).items():
        item = dict(latest)
        history = histories.get(str(symbol).upper(), {})
        if history:
            item.update(history)
            periods = int(history.get("history_periods_usd") or 0)
            if periods:
                attached += 1
            if periods >= 2:
                with_two_or_more += 1
        out[symbol] = item
    return out, {
        "history_attached_count": attached,
        "history_2plus_count": with_two_or_more,
        "method": "validated annual snapshots, comparable USD only",
    }
