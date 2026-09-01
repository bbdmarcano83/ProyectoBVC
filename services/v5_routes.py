"""Rutas V5 aisladas del monolito main.py.

Se incluyen mediante bootstrap FastAPI y mantienen autenticación/DB existentes.
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db, ActivoPortafolio, TransaccionHistorial
from services.auth import get_usuario_actual, suscripcion_activa
from services.bvc import obtener_datos_bvc, obtener_tasa_bcv, _to_float
from services.fx_history_v5 import get_close_rate
from services.ibc_history_v5 import load_ibc_history
from services.portfolio_benchmark_v5 import compare_open_portfolio_to_ibc, normalize_ibc_points, ibc_asof
from services.portfolio_snapshot_v5 import save_daily_snapshot, load_snapshots
from services.portfolio_performance_v5 import analyze_snapshot_performance

_ROUTER: APIRouter | None = None


def _tx_dict(tx: TransaccionHistorial) -> dict:
    raw_date = getattr(tx, "fecha", None)
    day = raw_date.date().isoformat() if hasattr(raw_date, "date") else str(raw_date or "")[:10]
    # La bitácora legacy podía guardar BCV actual aunque el usuario eligiera una
    # fecha histórica. Preferimos la tasa histórica persistida; si no existe,
    # dejamos FX nulo para no fabricar un benchmark USD.
    historical_fx = get_close_rate(day, refresh_if_missing=False) if day else None
    return {
        "simbolo": tx.simbolo,
        "tipo": tx.tipo,
        "cantidad": tx.cantidad,
        "precio": tx.precio,
        "fee_total": getattr(tx, "fee_total", None),
        "neto": getattr(tx, "neto", None),
        "fecha": day,
        "tasa_bcv": historical_fx,
        "tasa_bcv_legacy": getattr(tx, "tasa_bcv", None),
    }


def _position_dict(asset: ActivoPortafolio, price: float) -> dict:
    qty = _to_float(asset.cantidad)
    prom = _to_float(asset.precio_promedio)
    com = _to_float(asset.comision)
    reg = _to_float(asset.registro)
    iva = _to_float(asset.iva or 16)
    cost = qty * prom + com + reg + com * iva / 100.0
    created = getattr(asset, "creado_en", None)
    return {
        "simb": str(asset.simbolo or "").upper(),
        "cantidad": qty,
        "costo_total": cost,
        "val_mkt": qty * (_to_float(price) or prom),
        "creado_en": created.date().isoformat() if hasattr(created, "date") else (str(created)[:10] if created else None),
    }


def _audited_ibc_points() -> tuple[list[dict], dict]:
    points, meta = load_ibc_history()
    audited = [p for p in points if int(p.get("source_confidence") or 0) >= 75]
    out_meta = dict(meta)
    out_meta["benchmark_usable_points"] = len(audited)
    out_meta["legacy_untrusted_excluded"] = max(0, len(points) - len(audited))
    return audited, out_meta


def get_v5_router() -> APIRouter:
    global _ROUTER
    if _ROUTER is not None:
        return _ROUTER

    router = APIRouter()

    @router.get("/api/v5/portfolio-benchmark", response_class=JSONResponse)
    async def portfolio_benchmark_v5(request: Request, db: Session = Depends(get_db)):
        usuario = get_usuario_actual(request, db)
        if not usuario:
            return JSONResponse({"error": "No autorizado"}, status_code=401)
        if not suscripcion_activa(usuario):
            return JSONResponse({"error": "Suscripción requerida"}, status_code=403)

        datos_bolsa, current_fx = await asyncio.gather(obtener_datos_bvc(), obtener_tasa_bcv())
        prices = {
            str(item.get("COD_SIMB") or "").upper(): _to_float(item.get("PRECIO") or 0)
            for item in datos_bolsa
        }
        assets = db.query(ActivoPortafolio).filter(ActivoPortafolio.usuario_id == usuario.id).all()
        tx_rows = db.query(TransaccionHistorial).filter(
            TransaccionHistorial.usuario_id == usuario.id
        ).order_by(TransaccionHistorial.fecha.asc()).all()
        transactions = [_tx_dict(tx) for tx in tx_rows]
        positions = [_position_dict(a, prices.get(str(a.simbolo).upper(), 0.0)) for a in assets]

        ibc_raw, ibc_meta = _audited_ibc_points()
        normalized_ibc = normalize_ibc_points(ibc_raw)
        current_ibc = ibc_asof(normalized_ibc, date.today()) if normalized_ibc else None

        open_benchmark = compare_open_portfolio_to_ibc(
            positions,
            transactions,
            ibc_raw,
            current_ibc=current_ibc,
            current_fx=current_fx if current_fx > 0 else None,
        )

        snapshot_state = None
        try:
            snapshot_state = save_daily_snapshot(
                usuario.id,
                prices=prices,
                fx_bcv=current_fx if current_fx > 0 else None,
                ibc_level=current_ibc,
                source="portfolio_view",
            )
        except Exception as exc:
            snapshot_state = {"saved": False, "error": type(exc).__name__}

        snapshots = load_snapshots(usuario.id)
        temporal = analyze_snapshot_performance(snapshots, transactions)

        return JSONResponse({
            "engine_version": "v5-portfolio-benchmark",
            "as_of": date.today().isoformat(),
            "benchmark": open_benchmark,
            "performance": temporal,
            "ibc": ibc_meta,
            "snapshot": snapshot_state,
            "fx_current": current_fx if current_fx > 0 else None,
            "notes": [
                "Benchmark abierto: lotes FIFO y fechas equivalentes contra IBC.",
                "USD usa BCV histórico por fecha; si falta, no se aproxima.",
                "Ventanas temporales usan snapshots reales y Modified Dietz para corregir flujos.",
            ],
        })

    _ROUTER = router
    return router
