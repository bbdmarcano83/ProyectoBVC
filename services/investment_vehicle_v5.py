"""V5 scoring para fondos y vehículos de inversión listados en la BVC.

No aplica Greenblatt EBIT/EV ni Buffett operativo a un fondo. Usa únicamente
métricas compatibles con vehículos: NAV/patrimonio, descuento a NAV/libro,
ROA/rentabilidad del vehículo, distribuciones y consistencia histórica.
Los campos faltantes permanecen faltantes.
"""
from __future__ import annotations
from typing import Any

from services.fundamentals_v5 import load_fundamentals
from services.fundamental_sources_v5 import get_source


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _positive_ratio(values: Any) -> float | None:
    if not isinstance(values, list):
        return None
    clean = [_f(v) for v in values]
    clean = [v for v in clean if v is not None]
    if not clean:
        return None
    return sum(1 for v in clean if v > 0) / len(clean) * 100.0


def _growth(values: Any) -> float | None:
    if not isinstance(values, list):
        return None
    clean = [_f(v) for v in values]
    clean = [v for v in clean if v is not None]
    if len(clean) < 2 or clean[0] in (None, 0):
        return None
    years = len(clean) - 1
    if clean[0] > 0 and clean[-1] > 0:
        return ((clean[-1] / clean[0]) ** (1 / years) - 1) * 100.0
    return (clean[-1] / clean[0] - 1) * 100.0


def _percentile(rows: list[dict], key: str, higher: bool = True) -> dict[str, float]:
    pairs = [(str(r["simbolo"]), _f(r.get(key))) for r in rows if r.get("simbolo")]
    pairs = [(s, v) for s, v in pairs if v is not None]
    if not pairs:
        return {}
    vals = sorted(v for _, v in pairs)
    if len(vals) == 1:
        return {pairs[0][0]: 50.0}
    out = {}
    for symbol, value in pairs:
        below = sum(1 for x in vals if x < value)
        equal = sum(1 for x in vals if x == value)
        rank = (below + (equal - 1) / 2) / (len(vals) - 1) * 100.0
        out[symbol] = round(rank if higher else 100.0 - rank, 1)
    return out


def _weighted(parts: list[tuple[float | None, float]]) -> tuple[float | None, float]:
    available = [(v, w) for v, w in parts if v is not None]
    if not available:
        return None, 0.0
    weight = sum(w for _, w in available)
    total = sum(w for _, w in parts)
    return round(sum(float(v) * w for v, w in available) / weight, 1), round(weight / total * 100.0, 1)


def _vehicle_metrics(data: dict) -> dict:
    market_cap = _f(data.get("market_cap"))
    equity = _f(data.get("equity"))
    assets = _f(data.get("total_assets"))
    net_income = _f(data.get("net_income"))
    nav_per_share = _f(data.get("nav_per_share"))
    market_price = _f(data.get("market_price"))
    distribution_yield = _f(data.get("distribution_yield_pct"))
    pb = _div(market_cap, equity)
    roa = _div(net_income, assets)
    discount_nav = None
    if nav_per_share is not None and nav_per_share > 0 and market_price is not None:
        discount_nav = (nav_per_share - market_price) / nav_per_share * 100.0
    return {
        "vehicle_pb_v5": pb,
        "vehicle_roa_pct_v5": roa * 100.0 if roa is not None else None,
        "vehicle_discount_to_nav_pct_v5": discount_nav,
        "vehicle_distribution_yield_pct_v5": distribution_yield,
        "vehicle_positive_income_periods_pct_v5": _positive_ratio(data.get("earnings_history")),
        "vehicle_nav_cagr_pct_v5": _growth(data.get("nav_history")),
    }


def enrich_investment_vehicles(rows: list[dict]) -> tuple[list[dict], dict]:
    fundamentals, _ = load_fundamentals()
    vehicle_rows: list[dict] = []
    for row in rows:
        src = get_source(str(row.get("simbolo") or ""))
        if not src or src.get("industry_type") != "investment_vehicle":
            continue
        data = fundamentals.get(str(row.get("simbolo") or "").upper())
        if data is None:
            canonical = src.get("canonical_symbol")
            data = fundamentals.get(str(canonical or "").upper())
        row["industry_type_v5"] = "investment_vehicle"
        if not data:
            row["vehicle_score_v5"] = None
            row["vehicle_coverage_v5"] = 0.0
            continue
        row.update(_vehicle_metrics(data))
        vehicle_rows.append(row)

    specs = {
        "vehicle_discount_to_nav_pct_v5": True,
        "vehicle_pb_v5": False,
        "vehicle_roa_pct_v5": True,
        "vehicle_distribution_yield_pct_v5": True,
        "vehicle_positive_income_periods_pct_v5": True,
        "vehicle_nav_cagr_pct_v5": True,
    }
    ranks = {k: _percentile(vehicle_rows, k, high) for k, high in specs.items()}
    for row in vehicle_rows:
        sym = str(row.get("simbolo"))
        def r(key: str):
            return ranks[key].get(sym)
        score, coverage = _weighted([
            (r("vehicle_discount_to_nav_pct_v5"), 0.25),
            (r("vehicle_pb_v5"), 0.15),
            (r("vehicle_roa_pct_v5"), 0.20),
            (r("vehicle_distribution_yield_pct_v5"), 0.15),
            (r("vehicle_positive_income_periods_pct_v5"), 0.15),
            (r("vehicle_nav_cagr_pct_v5"), 0.10),
        ])
        row["vehicle_score_v5"] = score
        row["vehicle_coverage_v5"] = coverage
        # El score fundamental unificado usa esta ruta en vez de fingir
        # Greenblatt/Graham/Buffett operativo.
        row["greenblatt_score_v5"] = None
        row["graham_score_v5"] = None
        row["buffett_score_v5"] = None
        row["fundamental_score_v5"] = score
        row["fundamental_coverage_v5"] = coverage
        row["fundamental_method_v5"] = "investment_vehicle_nav_value_quality"

    return rows, {
        "vehicle_count": sum(1 for r in rows if r.get("industry_type_v5") == "investment_vehicle"),
        "vehicle_scored_count": sum(1 for r in rows if r.get("vehicle_score_v5") is not None),
        "method": "NAV/book discount + ROA + distributions + consistency",
    }
