"""Normalización cambiaria para fundamentales Caracas Bull V5.

Regla principal: nunca comparar estados venezolanos históricos usando sólo VES
nominales. Se conserva el dato original y se genera una vista USD trazable.

- Saldos de balance y valores por acción a fecha de corte: tasa BCV de cierre.
- Flujos del período: tasa BCV promedio del período cuando el estado es nominal.
- Estados reexpresados a moneda constante de cierre: tasa BCV de cierre para
  todas las partidas monetarias reexpresadas.

Nunca usa la tasa actual para convertir un estado histórico. Si falta la tasa
correspondiente, no se inventa USD y el snapshot queda con cobertura FX parcial.
"""
from __future__ import annotations

from typing import Any

BALANCE_FIELDS = {
    "total_assets", "total_liabilities", "equity", "cash", "total_debt",
    "current_assets", "current_liabilities", "net_ppe", "nav", "market_cap",
    "nav_per_share", "market_price",
}

FLOW_FIELDS = {
    "revenue", "ebit", "net_income", "free_cash_flow", "operating_cash_flow",
    "capex", "distribution_per_share",
}

NON_MONETARY_FIELDS = {
    "shares_outstanding", "distribution_yield_pct",
}

ALLOWED_BASES = {"nominal_ves", "constant_ves_end_period", "usd_reported"}


def _f(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_fx_metadata(data: dict) -> dict:
    currency = str(data.get("currency") or "").upper().strip()
    basis = str(data.get("monetary_basis") or "nominal_ves").strip().lower()
    close_rate = _f(data.get("fx_rate_bcv_close"))
    avg_rate = _f(data.get("fx_rate_bcv_avg"))
    source = str(data.get("fx_source_url") or "").strip()
    fx_as_of = str(data.get("fx_as_of") or "").strip()
    flags: list[str] = []

    if currency in {"USD", "US$"}:
        basis = "usd_reported"
    if basis not in ALLOWED_BASES:
        flags.append("invalid_monetary_basis")
    if basis != "usd_reported":
        if close_rate is None or close_rate <= 0:
            flags.append("missing_bcv_close_rate")
        if basis == "nominal_ves" and (avg_rate is None or avg_rate <= 0):
            flags.append("missing_bcv_average_rate")
        if not source.startswith("https://"):
            flags.append("missing_official_fx_source")
        if not fx_as_of:
            flags.append("missing_fx_as_of")

    return {
        "valid": not flags,
        "flags": flags,
        "currency": currency,
        "monetary_basis": basis,
        "fx_rate_bcv_close": close_rate,
        "fx_rate_bcv_avg": avg_rate,
        "fx_source_url": source or None,
        "fx_as_of": fx_as_of or None,
    }


def normalize_to_usd(data: dict) -> tuple[dict, dict]:
    """Return a copy with `<field>_usd` values and auditable FX metadata."""
    out = dict(data or {})
    meta = validate_fx_metadata(out)
    basis = meta["monetary_basis"]
    close_rate = meta["fx_rate_bcv_close"]
    avg_rate = meta["fx_rate_bcv_avg"]
    converted = 0
    eligible = 0

    if basis == "usd_reported":
        for field in BALANCE_FIELDS | FLOW_FIELDS:
            value = _f(out.get(field))
            if value is not None:
                eligible += 1
                out[f"{field}_usd"] = value
                converted += 1
        out["fx_normalization_method_v5"] = "reported_usd"
    else:
        for field in BALANCE_FIELDS:
            value = _f(out.get(field))
            if value is None:
                continue
            eligible += 1
            if close_rate and close_rate > 0:
                out[f"{field}_usd"] = value / close_rate
                converted += 1

        flow_rate = close_rate if basis == "constant_ves_end_period" else avg_rate
        for field in FLOW_FIELDS:
            value = _f(out.get(field))
            if value is None:
                continue
            eligible += 1
            if flow_rate and flow_rate > 0:
                out[f"{field}_usd"] = value / flow_rate
                converted += 1

        out["fx_normalization_method_v5"] = (
            "bcv_close_all_constant_ves" if basis == "constant_ves_end_period"
            else "bcv_close_balance_avg_flows"
        )

    out["fx_rate_bcv_close_v5"] = close_rate
    out["fx_rate_bcv_avg_v5"] = avg_rate
    out["fx_source_v5"] = meta["fx_source_url"]
    out["fx_as_of_v5"] = meta["fx_as_of"]
    out["monetary_basis_v5"] = basis
    out["fx_coverage_pct_v5"] = round(converted / max(1, eligible) * 100.0, 1) if eligible else 0.0

    meta.update({
        "eligible_fields": eligible,
        "converted_fields": converted,
        "coverage_pct": out["fx_coverage_pct_v5"],
    })
    return out, meta


def prefer_usd(data: dict, field: str) -> float | None:
    """Use normalized USD when available, otherwise the reported field."""
    usd = _f(data.get(f"{field}_usd"))
    return usd if usd is not None else _f(data.get(field))
