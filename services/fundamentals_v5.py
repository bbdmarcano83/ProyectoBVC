"""Fundamental engine V5 for Caracas Bull.

Greenblatt + Graham + Buffett with dedicated financial/investment-vehicle paths.
Historical Venezuelan statements are analyzed through an auditable USD view
when BCV FX metadata is available. Original reported values remain untouched in
storage; missing FX is never guessed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from services.fx_normalization_v5 import normalize_to_usd, prefer_usd


def _f(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _pct(v: float | None) -> float | None:
    return None if v is None else v * 100.0


def _positive_ratio(values: list[Any]) -> float | None:
    clean = [_f(v) for v in values]
    clean = [v for v in clean if v is not None]
    if not clean:
        return None
    return sum(1 for v in clean if v > 0) / len(clean) * 100.0


def _growth(values: list[Any]) -> float | None:
    clean = [_f(v) for v in values]
    clean = [v for v in clean if v is not None]
    if len(clean) < 2 or clean[0] == 0:
        return None
    years = len(clean) - 1
    if clean[0] > 0 and clean[-1] > 0:
        return ((clean[-1] / clean[0]) ** (1.0 / years) - 1.0) * 100.0
    return (clean[-1] / clean[0] - 1.0) * 100.0


def _normalize_payload(payload: Any) -> dict[str, dict] | None:
    if isinstance(payload, dict) and isinstance(payload.get("symbols"), dict):
        payload = payload["symbols"]
    if isinstance(payload, list):
        mapped: dict[str, dict] = {}
        for item in payload:
            if isinstance(item, dict) and item.get("simbolo"):
                mapped[str(item["simbolo"]).upper()] = item
        payload = mapped
    if not isinstance(payload, dict):
        return None
    return {str(symbol).upper(): data for symbol, data in payload.items() if isinstance(data, dict)}


def load_fundamentals() -> tuple[dict[str, dict], dict]:
    """Load only auditable snapshots; never infer missing values or FX."""
    try:
        from services.fundamental_store_v5 import load_latest_validated
        db_payload, db_meta = load_latest_validated()
        if db_payload:
            return db_payload, db_meta
    except Exception as exc:
        db_meta = {"source": "database:fundamental_snapshots", "available": False, "count": 0,
                   "error": type(exc).__name__}
    else:
        db_meta = {"source": "database:fundamental_snapshots", "available": False, "count": 0}

    raw = os.getenv("FUNDAMENTALS_V5_JSON", "").strip()
    source = "none"
    if raw:
        source = "env:FUNDAMENTALS_V5_JSON"
    else:
        path = os.getenv("FUNDAMENTALS_V5_PATH", "").strip()
        if path:
            p = Path(path)
            if p.exists() and p.is_file():
                raw = p.read_text(encoding="utf-8")
                source = f"file:{p.name}"
    if not raw:
        return {}, {**db_meta, "fallback_source": source}
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}, {"source": source, "available": False, "count": 0, "error": "invalid_json"}
    normalized = _normalize_payload(payload)
    if normalized is None:
        return {}, {"source": source, "available": False, "count": 0, "error": "invalid_shape"}
    return normalized, {"source": source, "available": bool(normalized), "count": len(normalized),
                        "persistent_store_empty": True}


def _is_financial(data: dict, sector: str = "") -> bool:
    kind = str(data.get("industry_type") or "").strip().lower()
    if kind in {"financial", "bank", "banking", "insurance"}:
        return True
    text = f"{sector} {data.get('sector','')}".lower()
    return any(k in text for k in ("banco", "bank", "financ", "seguro", "insurance"))


def _series(data: dict, base: str) -> list[Any]:
    usd_key = f"{base}_usd"
    if isinstance(data.get(usd_key), list):
        return data[usd_key]
    values = data.get(base)
    return values if isinstance(values, list) else []


def compute_metrics(data: dict, sector: str = "") -> dict:
    """Compute metrics from USD-normalized monetary fields when available."""
    fx_data, fx_meta = normalize_to_usd(data)

    market_cap = prefer_usd(fx_data, "market_cap")
    debt = prefer_usd(fx_data, "total_debt")
    cash = prefer_usd(fx_data, "cash")
    ebit = prefer_usd(fx_data, "ebit")
    net_income = prefer_usd(fx_data, "net_income")
    equity = prefer_usd(fx_data, "equity")
    assets = prefer_usd(fx_data, "total_assets")
    revenue = prefer_usd(fx_data, "revenue")
    fcf = prefer_usd(fx_data, "free_cash_flow")
    current_assets = prefer_usd(fx_data, "current_assets")
    current_liabilities = prefer_usd(fx_data, "current_liabilities")
    net_ppe = prefer_usd(fx_data, "net_ppe")

    financial = _is_financial(fx_data, sector)
    out: dict[str, Any] = {"industry_type_v5": "financial" if financial else "non_financial"}
    for key in (
        "fx_rate_bcv_close_v5", "fx_rate_bcv_avg_v5", "fx_source_v5", "fx_as_of_v5",
        "monetary_basis_v5", "fx_coverage_pct_v5", "fx_normalization_method_v5",
    ):
        out[key] = fx_data.get(key)
    out["fx_valid_v5"] = bool(fx_meta.get("valid"))
    out["fx_flags_v5"] = list(fx_meta.get("flags") or [])

    out["roe_pct_v5"] = _pct(_safe_div(net_income, equity))
    out["roa_pct_v5"] = _pct(_safe_div(net_income, assets))
    out["fcf_margin_pct_v5"] = _pct(_safe_div(fcf, revenue))
    out["net_margin_pct_v5"] = _pct(_safe_div(net_income, revenue))
    out["current_ratio_v5"] = _safe_div(current_assets, current_liabilities)
    out["debt_to_equity_v5"] = _safe_div(debt, equity)

    earnings_history = _series(fx_data, "earnings_history")
    revenue_history = _series(fx_data, "revenue_history")
    fcf_history = _series(fx_data, "fcf_history")
    out["positive_earnings_years_pct_v5"] = _positive_ratio(earnings_history)
    out["positive_fcf_years_pct_v5"] = _positive_ratio(fcf_history)
    out["earnings_cagr_pct_v5"] = _growth(earnings_history)
    out["revenue_cagr_pct_v5"] = _growth(revenue_history)

    if financial:
        out["pb_v5"] = _safe_div(market_cap, equity)
        out["pe_v5"] = _safe_div(market_cap, net_income) if net_income is not None and net_income > 0 else None
        out["earnings_yield_pct_v5"] = _pct(_safe_div(net_income, market_cap))
        out["return_on_capital_pct_v5"] = None
        out["enterprise_value_v5"] = None
    else:
        ev = market_cap + debt - cash if market_cap is not None and debt is not None and cash is not None else None
        nwc = current_assets - current_liabilities if current_assets is not None and current_liabilities is not None else None
        capital = nwc + net_ppe if nwc is not None and net_ppe is not None else None
        out["enterprise_value_v5"] = ev
        out["earnings_yield_pct_v5"] = _pct(_safe_div(ebit, ev))
        out["return_on_capital_pct_v5"] = _pct(_safe_div(ebit, capital))
        out["pb_v5"] = _safe_div(market_cap, equity)
        out["pe_v5"] = _safe_div(market_cap, net_income) if net_income is not None and net_income > 0 else None

    out["source_v5"] = data.get("source")
    out["as_of_v5"] = data.get("as_of")
    out["fundamental_fields_v5"] = sorted(k for k, v in data.items() if v not in (None, "", []))
    return out


def percentile_map(rows: list[dict], key: str, higher_is_better: bool = True) -> dict[str, float]:
    pairs = [(str(r["simbolo"]), _f(r.get(key))) for r in rows if r.get("simbolo")]
    pairs = [(s, v) for s, v in pairs if v is not None]
    vals = sorted(v for _, v in pairs)
    if not vals:
        return {}
    if len(vals) == 1:
        return {pairs[0][0]: 50.0}
    out: dict[str, float] = {}
    for symbol, value in pairs:
        below = sum(1 for x in vals if x < value)
        equal = sum(1 for x in vals if x == value)
        rank = (below + (equal - 1) / 2.0) / (len(vals) - 1) * 100.0
        out[symbol] = round(rank if higher_is_better else 100.0 - rank, 1)
    return out


def _avg_available(parts: list[tuple[float | None, float]]) -> tuple[float | None, float]:
    available = [(v, w) for v, w in parts if v is not None]
    if not available:
        return None, 0.0
    total_w = sum(w for _, w in available)
    score = sum(float(v) * w for v, w in available) / total_w
    coverage = total_w / sum(w for _, w in parts) * 100.0
    return round(score, 1), round(coverage, 1)


def enrich_fundamental_scores(market_rows: list[dict]) -> tuple[list[dict], dict]:
    fundamentals, meta = load_fundamentals()
    enriched: list[dict] = []
    calc_rows: list[dict] = []
    from services.fundamental_sources_v5 import get_source

    for row in market_rows:
        item = dict(row)
        symbol = str(item.get("simbolo") or "").upper()
        src = get_source(symbol)
        canonical = str(src.get("canonical_symbol") if src else symbol).upper()
        data = fundamentals.get(symbol) or fundamentals.get(canonical)
        if not data:
            item["fundamentals_available_v5"] = False
            enriched.append(item)
            continue
        if src and src.get("industry_type") == "investment_vehicle":
            item["fundamentals_available_v5"] = True
            item["industry_type_v5"] = "investment_vehicle"
            enriched.append(item)
            continue
        item.update(compute_metrics(data, str(item.get("sector") or "")))
        item["fundamentals_available_v5"] = True
        calc_rows.append(item)
        enriched.append(item)

    if not calc_rows:
        meta.update({"coverage_pct": 0.0, "scored_count": 0})
        return enriched, meta

    specs = {
        "earnings_yield_pct_v5": True, "return_on_capital_pct_v5": True,
        "roe_pct_v5": True, "roa_pct_v5": True, "fcf_margin_pct_v5": True,
        "net_margin_pct_v5": True, "positive_earnings_years_pct_v5": True,
        "positive_fcf_years_pct_v5": True, "earnings_cagr_pct_v5": True,
        "revenue_cagr_pct_v5": True, "current_ratio_v5": True,
        "debt_to_equity_v5": False, "pb_v5": False, "pe_v5": False,
    }
    ranks = {key: percentile_map(calc_rows, key, high) for key, high in specs.items()}

    for item in enriched:
        if not item.get("fundamentals_available_v5") or item.get("industry_type_v5") == "investment_vehicle":
            continue
        sym = str(item.get("simbolo"))
        r = lambda key: ranks.get(key, {}).get(sym)
        financial = item.get("industry_type_v5") == "financial"
        if financial:
            greenblatt, green_cov = _avg_available([(r("roe_pct_v5"), .35), (r("roa_pct_v5"), .20), (r("pb_v5"), .25), (r("pe_v5"), .20)])
        else:
            greenblatt, green_cov = _avg_available([(r("return_on_capital_pct_v5"), .55), (r("earnings_yield_pct_v5"), .45)])
        graham, graham_cov = _avg_available([(r("current_ratio_v5"), .20), (r("debt_to_equity_v5"), .20), (r("positive_earnings_years_pct_v5"), .25), (r("pb_v5"), .15), (r("pe_v5"), .20)])
        buffett, buffett_cov = _avg_available([(r("roe_pct_v5"), .25), (r("roa_pct_v5"), .10), (r("fcf_margin_pct_v5"), .20), (r("net_margin_pct_v5"), .10), (r("positive_fcf_years_pct_v5"), .15), (r("earnings_cagr_pct_v5"), .10), (r("revenue_cagr_pct_v5"), .10)])
        philosophy, philosophy_cov = _avg_available([(greenblatt, .35), (graham, .25), (buffett, .40)])
        item.update({
            "greenblatt_score_v5": greenblatt, "graham_score_v5": graham,
            "buffett_score_v5": buffett, "fundamental_score_v5": philosophy,
            "greenblatt_coverage_v5": green_cov, "graham_coverage_v5": graham_cov,
            "buffett_coverage_v5": buffett_cov, "fundamental_coverage_v5": philosophy_cov,
        })

    scored = sum(1 for r in enriched if r.get("fundamental_score_v5") is not None)
    fx_ready = sum(1 for r in enriched if r.get("fx_valid_v5"))
    meta.update({
        "coverage_pct": round(scored / max(1, len(market_rows)) * 100.0, 1),
        "scored_count": scored,
        "fx_ready_count": fx_ready,
        "method": "Greenblatt + Graham + Buffett on auditable USD/BCV view, with dedicated financials/investment-vehicle paths",
    })
    return enriched, meta
