"""Tendencia fundamental V5 basada exclusivamente en series comparables en USD.

No modifica todavía el peso del score fundamental. Produce una capa explicativa
que podrá incorporarse a pesos después de backtest/walk-forward suficiente.
"""
from __future__ import annotations

import json
from typing import Any

from database import SessionLocal, FundamentalSnapshot

TREND_FIELDS = ("equity", "revenue", "net_income", "free_cash_flow", "nav", "total_assets")


def _f(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def comparable_usd_value(data: dict, field: str) -> float | None:
    """Only returns values genuinely comparable across periods."""
    usd = _f(data.get(f"{field}_usd"))
    if usd is not None:
        return usd
    currency = str(data.get("currency") or "").upper().strip()
    if currency in {"USD", "US$"}:
        return _f(data.get(field))
    return None


def load_validated_history() -> dict[str, list[dict]]:
    """Load all validated snapshots grouped chronologically by canonical symbol."""
    with SessionLocal() as db:
        rows = db.query(FundamentalSnapshot).filter(
            FundamentalSnapshot.validated.is_(True)
        ).order_by(
            FundamentalSnapshot.simbolo.asc(),
            FundamentalSnapshot.as_of.asc(),
            FundamentalSnapshot.id.asc(),
        ).all()

    out: dict[str, list[dict]] = {}
    for row in rows:
        try:
            data = json.loads(row.data_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        item = dict(data)
        item["as_of"] = row.as_of
        item["validation_score"] = row.validation_score
        out.setdefault(str(row.simbolo).upper(), []).append(item)
    return out


def _pct_change(previous: float | None, current: float | None) -> float | None:
    if previous is None or current is None or abs(previous) < 1e-12:
        return None
    return (current / previous - 1.0) * 100.0


def compute_fundamental_trend(history: list[dict]) -> dict:
    """Compare first vs latest usable USD observation for each supported field."""
    if not isinstance(history, list) or len(history) < 2:
        return {
            "label": "SIN HISTORIA SUFICIENTE",
            "coverage_pct": 0.0,
            "periods": len(history) if isinstance(history, list) else 0,
            "changes": {},
            "positive": 0,
            "negative": 0,
        }

    changes: dict[str, float] = {}
    for field in TREND_FIELDS:
        observations = [comparable_usd_value(item, field) for item in history]
        observations = [x for x in observations if x is not None]
        if len(observations) < 2:
            continue
        change = _pct_change(observations[0], observations[-1])
        if change is not None:
            changes[field] = round(change, 2)

    if not changes:
        return {
            "label": "FX/HISTORIA INSUFICIENTE",
            "coverage_pct": 0.0,
            "periods": len(history),
            "changes": {},
            "positive": 0,
            "negative": 0,
        }

    # Umbral de ±3% para evitar declarar tendencia por ruido mínimo.
    positive = sum(1 for v in changes.values() if v > 3.0)
    negative = sum(1 for v in changes.values() if v < -3.0)
    neutral = len(changes) - positive - negative
    if positive >= negative + 2:
        label = "MEJORANDO"
    elif negative >= positive + 2:
        label = "DETERIORANDO"
    else:
        label = "ESTABLE/MIXTO"

    return {
        "label": label,
        "coverage_pct": round(len(changes) / len(TREND_FIELDS) * 100.0, 1),
        "periods": len(history),
        "first_as_of": history[0].get("as_of"),
        "latest_as_of": history[-1].get("as_of"),
        "changes": changes,
        "positive": positive,
        "negative": negative,
        "neutral": neutral,
        "method": "first_vs_latest_comparable_usd",
    }


def attach_fundamental_trends(rows: list[dict]) -> tuple[list[dict], dict]:
    histories = load_validated_history()
    attached = 0
    improving = 0
    deteriorating = 0
    for row in rows:
        symbol = str(row.get("simbolo") or "").upper()
        # scoring rows may be aliases; use source registry canonical symbol.
        try:
            from services.fundamental_sources_v5 import get_source
            src = get_source(symbol)
            canonical = str(src.get("canonical_symbol") if src else symbol).upper()
        except Exception:
            canonical = symbol
        trend = compute_fundamental_trend(histories.get(canonical, []))
        row["fundamental_trend_v5"] = trend["label"]
        row["fundamental_trend_coverage_v5"] = trend["coverage_pct"]
        row["fundamental_trend_periods_v5"] = trend["periods"]
        row["fundamental_trend_changes_v5"] = trend["changes"]
        if trend["coverage_pct"] > 0:
            attached += 1
        if trend["label"] == "MEJORANDO":
            improving += 1
        elif trend["label"] == "DETERIORANDO":
            deteriorating += 1
    return rows, {
        "trend_attached_count": attached,
        "improving_count": improving,
        "deteriorating_count": deteriorating,
        "method": "USD-normalized multi-period trend; informational until backtested",
    }
