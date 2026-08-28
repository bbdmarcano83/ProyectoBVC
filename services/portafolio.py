"""Runtime facade for ProyectoBVC Portfolio Engine V4.

Mantiene las funciones legacy y añade inteligencia V4 sin requerir persistencia.
Rollback: PORTFOLIO_ENGINE_V4_ENABLED=false.
"""
from __future__ import annotations

import os

from services.portafolio_legacy import *
from services.portafolio_legacy import calcular_fila as _calcular_fila_legacy
from services.portafolio_legacy import resumen_portafolio as _resumen_legacy
from services.bvc import _to_float


def _enabled() -> bool:
    raw = os.environ.get("PORTFOLIO_ENGINE_V4_ENABLED", "true")
    return raw.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def calcular_fila(simb: str, datos: dict, precio_actual: float, total_mkt: float, tasa: float) -> dict:
    return _calcular_fila_legacy(simb, datos, precio_actual, total_mkt, tasa)


def resumen_portafolio(portafolio: dict, datos_bolsa: list, tasa: float) -> dict:
    resumen = _resumen_legacy(portafolio, datos_bolsa, tasa)
    if not _enabled():
        return resumen

    mapa = {item.get("COD_SIMB"): item for item in datos_bolsa if item.get("COD_SIMB")}
    total_mkt = 0.0
    for simb, datos in portafolio.items():
        cantidad = _to_float(datos.get("cantidad"))
        prom = _to_float(datos.get("precio_promedio"))
        precio = _to_float(mapa.get(simb, {}).get("PRECIO") or prom)
        total_mkt += cantidad * precio

    filas = []
    for simb, datos in portafolio.items():
        prom = _to_float(datos.get("precio_promedio"))
        precio = _to_float(mapa.get(simb, {}).get("PRECIO") or prom)
        filas.append(_calcular_fila_legacy(simb, datos, precio, total_mkt, tasa))

    scoring_map = {}
    try:
        from services.scoring_engine_v3 import get_last_scoring_map
        scoring_map = get_last_scoring_map()
    except Exception:
        scoring_map = {}

    from services.portfolio_v4 import enriquecer_resumen_v4
    enriched = enriquecer_resumen_v4(resumen, filas, scoring_map)
    enriched["engine_version"] = "v4-stateless-full"
    enriched["storage"] = "stateless"
    return enriched
