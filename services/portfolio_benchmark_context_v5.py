"""Adaptador runtime para exponer Portafolio vs IBC sin acoplar el motor puro.

El feature queda apagado por defecto. Cuando se active, usa la sesión SQL de la
ruta para leer la bitácora del usuario, combina fechas reales de las posiciones
y carga la serie IBC ya persistida/auditada. No modifica posiciones ni trades.
"""
from __future__ import annotations

import os
from typing import Any, Iterable

from database import TransaccionHistorial
from services.ibc_store_v5 import load_persisted_ibc
from services.portfolio_benchmark_v5 import compare_open_portfolio_to_ibc

FLAG_NAME = "PORTFOLIO_IBC_BENCHMARK_V5_ENABLED"


def enabled() -> bool:
    return str(os.environ.get(FLAG_NAME, "false")).strip().lower() in {
        "1", "true", "yes", "on", "enabled"
    }


def _isoish(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return value


def _position_rows(activos_db: Iterable[Any], filas: Iterable[dict]) -> list[dict]:
    meta = {
        str(getattr(a, "simbolo", "") or "").upper(): a
        for a in (activos_db or [])
        if str(getattr(a, "simbolo", "") or "").strip()
    }
    out: list[dict] = []
    for raw in filas or []:
        fila = dict(raw)
        symbol = str(fila.get("simb") or fila.get("simbolo") or "").upper()
        activo = meta.get(symbol)
        if activo is not None:
            fila["creado_en"] = _isoish(getattr(activo, "creado_en", None))
        out.append(fila)
    return out


def _transaction_dict(row: Any) -> dict:
    fields = (
        "simbolo", "tipo", "cantidad", "precio", "comision", "registro", "iva",
        "fecha", "notas", "motivo", "tasa_bcv", "score", "fee_total", "neto",
    )
    return {key: _isoish(getattr(row, key, None)) for key in fields}


def attach_portfolio_benchmark_v5(
    resumen: dict,
    *,
    db,
    user_id: int,
    activos_db: Iterable[Any],
    filas: Iterable[dict],
    current_fx: float | None,
) -> dict:
    """Adjunta `portfolio_benchmark_v5` sólo cuando el feature flag está activo."""
    if not enabled():
        return resumen

    enriched = dict(resumen or {})
    try:
        tx_rows = db.query(TransaccionHistorial).filter(
            TransaccionHistorial.usuario_id == int(user_id)
        ).order_by(TransaccionHistorial.fecha.asc(), TransaccionHistorial.id.asc()).all()
        transactions = [_transaction_dict(row) for row in tx_rows]
        positions = _position_rows(activos_db, filas)
        ibc_points, ibc_meta = load_persisted_ibc()
        benchmark = compare_open_portfolio_to_ibc(
            positions,
            transactions,
            ibc_points,
            current_fx=current_fx,
        )
        benchmark = dict(benchmark)
        benchmark["ibc_source"] = ibc_meta.get("source")
        benchmark["ibc_points"] = ibc_meta.get("count", 0)
        benchmark["ibc_official_points"] = ibc_meta.get("official_points", 0)
        benchmark["feature_flag"] = FLAG_NAME
        enriched["portfolio_benchmark_v5"] = benchmark
    except Exception as exc:
        enriched["portfolio_benchmark_v5"] = {
            "available": False,
            "reason": "benchmark_runtime_error",
            "error_type": type(exc).__name__,
            "feature_flag": FLAG_NAME,
        }
    return enriched
