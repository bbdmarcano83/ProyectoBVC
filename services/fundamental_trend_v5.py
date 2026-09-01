"""Tendencia fundamental V5 basada exclusivamente en series anuales comparables en USD.

La capa es informativa: NO modifica todavía el peso del score V5. La fuente de
verdad para comparabilidad es `fundamental_history_v5`, evitando que un snapshot
trimestral/semestral se mezcle accidentalmente con ejercicios FY.
"""
from __future__ import annotations

from typing import Any

from services.fundamental_history_v5 import load_comparable_histories

TREND_FIELDS_BY_TYPE = {
    "financial": ("equity", "net_income", "total_assets"),
    "non_financial": ("equity", "revenue", "net_income", "free_cash_flow", "total_assets"),
    "investment_vehicle": ("equity", "net_income", "nav", "total_assets"),
}
DEFAULT_TREND_FIELDS = ("equity", "revenue", "net_income", "free_cash_flow", "nav", "total_assets")
SERIES_KEY = {
    "equity": "equity_history_usd",
    "revenue": "revenue_history_usd",
    "net_income": "earnings_history_usd",
    "free_cash_flow": "fcf_history_usd",
    "nav": "nav_history_usd",
    "total_assets": "assets_history_usd",
}


def _f(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def comparable_usd_value(data: dict, field: str) -> float | None:
    """Devuelve sólo cifras explícitamente comparables en USD."""
    usd = _f(data.get(f"{field}_usd"))
    if usd is not None:
        return usd
    currency = str(data.get("currency") or "").upper().strip()
    if currency in {"USD", "US$"}:
        return _f(data.get(field))
    return None


def _pct_change(previous: float | None, current: float | None) -> float | None:
    if previous is None or current is None or abs(previous) < 1e-12:
        return None
    return (current / previous - 1.0) * 100.0


def _classify(changes: dict[str, float], *, periods: int, coverage_pct: float,
              first_as_of: str | None = None, latest_as_of: str | None = None) -> dict:
    if periods < 2:
        return {
            "label": "SIN HISTORIA SUFICIENTE",
            "coverage_pct": 0.0,
            "periods": periods,
            "changes": {},
            "positive": 0,
            "negative": 0,
        }
    if not changes:
        return {
            "label": "FX/HISTORIA INSUFICIENTE",
            "coverage_pct": 0.0,
            "periods": periods,
            "changes": {},
            "positive": 0,
            "negative": 0,
        }

    # ±3% evita etiquetar ruido mínimo como tendencia estructural.
    positive = sum(1 for value in changes.values() if value > 3.0)
    negative = sum(1 for value in changes.values() if value < -3.0)
    neutral = len(changes) - positive - negative
    if positive >= negative + 2:
        label = "MEJORANDO"
    elif negative >= positive + 2:
        label = "DETERIORANDO"
    else:
        label = "ESTABLE/MIXTO"

    return {
        "label": label,
        "coverage_pct": round(coverage_pct, 1),
        "periods": periods,
        "first_as_of": first_as_of,
        "latest_as_of": latest_as_of,
        "changes": changes,
        "positive": positive,
        "negative": negative,
        "neutral": neutral,
        "method": "first_vs_latest_annual_comparable_usd",
    }


def compute_fundamental_trend(history: list[dict], industry_type: str | None = None) -> dict:
    """API pura/compatible para tests: compara observaciones USD ya filtradas.

    Quien llame esta función es responsable de entregar períodos comparables.
    El adaptador de producción no usa snapshots crudos: usa
    `compute_fundamental_trend_from_series` sobre la serie anual canónica.
    """
    if not isinstance(history, list) or len(history) < 2:
        return _classify({}, periods=len(history) if isinstance(history, list) else 0, coverage_pct=0.0)

    fields = TREND_FIELDS_BY_TYPE.get(str(industry_type or "").lower(), DEFAULT_TREND_FIELDS)
    changes: dict[str, float] = {}
    for field in fields:
        observations = [comparable_usd_value(item, field) for item in history]
        observations = [value for value in observations if value is not None]
        if len(observations) < 2:
            continue
        change = _pct_change(observations[0], observations[-1])
        if change is not None:
            changes[field] = round(change, 2)

    coverage = len(changes) / len(fields) * 100.0 if fields else 0.0
    return _classify(
        changes,
        periods=len(history),
        coverage_pct=coverage,
        first_as_of=str(history[0].get("as_of") or "")[:10] or None,
        latest_as_of=str(history[-1].get("as_of") or "")[:10] or None,
    )


def compute_fundamental_trend_from_series(series: dict, industry_type: str | None = None) -> dict:
    """Calcula tendencia desde la serie anual comparable canónica del store."""
    periods = int((series or {}).get("history_periods_usd") or 0)
    fields = TREND_FIELDS_BY_TYPE.get(str(industry_type or "").lower(), DEFAULT_TREND_FIELDS)
    changes: dict[str, float] = {}
    used_dates: list[str] = []

    for field in fields:
        key = SERIES_KEY[field]
        values = [_f(value) for value in ((series or {}).get(key) or [])]
        values = [value for value in values if value is not None]
        dates = [str(value)[:10] for value in ((series or {}).get(f"{key}_dates") or []) if value]
        if len(values) < 2:
            continue
        change = _pct_change(values[0], values[-1])
        if change is None:
            continue
        changes[field] = round(change, 2)
        if dates:
            used_dates.extend((dates[0], dates[-1]))

    coverage = len(changes) / len(fields) * 100.0 if fields else 0.0
    history_dates = [str(value)[:10] for value in ((series or {}).get("history_dates_usd") or []) if value]
    first = history_dates[0] if history_dates else (min(used_dates) if used_dates else None)
    latest = history_dates[-1] if history_dates else (max(used_dates) if used_dates else None)
    out = _classify(changes, periods=periods, coverage_pct=coverage, first_as_of=first, latest_as_of=latest)
    out["history_basis_v5"] = (series or {}).get("history_basis_v5")
    return out


def attach_fundamental_trends(rows: list[dict]) -> tuple[list[dict], dict]:
    """Adjunta trend sin consultar snapshots crudos ni mezclar FY con Q/H."""
    histories = load_comparable_histories()
    attached = 0
    improving = 0
    deteriorating = 0

    for row in rows:
        symbol = str(row.get("simbolo") or "").upper()
        try:
            from services.fundamental_sources_v5 import get_source
            source = get_source(symbol)
            canonical = str(source.get("canonical_symbol") if source else symbol).upper()
            industry_type = str(row.get("industry_type_v5") or (source or {}).get("industry_type") or "").lower()
        except Exception:
            canonical = symbol
            industry_type = str(row.get("industry_type_v5") or "").lower()

        trend = compute_fundamental_trend_from_series(histories.get(canonical, {}), industry_type)
        row["fundamental_trend_v5"] = trend["label"]
        row["fundamental_trend_coverage_v5"] = trend["coverage_pct"]
        row["fundamental_trend_periods_v5"] = trend["periods"]
        row["fundamental_trend_changes_v5"] = trend["changes"]
        row["fundamental_trend_first_as_of_v5"] = trend.get("first_as_of")
        row["fundamental_trend_latest_as_of_v5"] = trend.get("latest_as_of")
        row["fundamental_trend_basis_v5"] = trend.get("history_basis_v5")

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
        "method": "annual comparable USD only; informational until backtested",
    }
