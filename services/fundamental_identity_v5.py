"""Identidad económica estable para documentos fundamentales V5.

La identidad técnica de una ingesta puede cambiar cuando mejora la normalización
FX, metadata o campos derivados. Esta capa construye una firma separada usando
sólo cifras reportadas/originales y el contexto contable necesario para decidir
si dos snapshots representan el mismo documento económico.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

# Campos económicos reportados por el emisor. Se excluye market_cap porque es
# una valoración de mercado, no una cifra del estado financiero.
REPORTED_NUMERIC_FIELDS = {
    "total_debt",
    "cash",
    "ebit",
    "net_income",
    "equity",
    "total_assets",
    "total_liabilities",
    "revenue",
    "free_cash_flow",
    "current_assets",
    "current_liabilities",
    "net_ppe",
    "operating_cash_flow",
    "capex",
    "shares_outstanding",
    "nav",
    "distribution_per_share",
}

REPORTING_CONTEXT_FIELDS = {
    "currency",
    "monetary_basis",
    "industry_type",
}


def _canonical_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _numeric(value: Any) -> float | Any:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return value
    return result if math.isfinite(result) else value


def _context(key: str, value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if key == "currency":
        return text.upper()
    if key in {"monetary_basis", "industry_type"}:
        return text.lower()
    return text


def economic_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Devuelve sólo la parte económica estable de un snapshot.

    Deliberadamente ignora `*_usd`, `fx_*`, `market_*`, `valuation_*`, hashes,
    fuentes y demás metadata derivada. Un cambio de conversión no debe crear un
    nuevo documento económico; un cambio en una cifra reportada sí.
    """
    if not isinstance(payload, dict):
        return {}

    out: dict[str, Any] = {}
    for key in sorted(REPORTED_NUMERIC_FIELDS):
        value = payload.get(key)
        if value not in (None, ""):
            out[key] = _numeric(value)
    for key in sorted(REPORTING_CONTEXT_FIELDS):
        value = payload.get(key)
        if value not in (None, ""):
            out[key] = _context(key, value)
    return out


def economic_signature(source_url: str, as_of: str, payload: dict[str, Any] | None) -> str:
    basis = f"{str(source_url or '').strip()}|{str(as_of or '').strip()}|{_canonical_json(economic_payload(payload))}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()
