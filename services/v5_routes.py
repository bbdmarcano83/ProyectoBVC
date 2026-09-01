"""Rutas V5 aisladas del monolito main.py.

El handler se expone a nivel de módulo para que el bootstrap pueda registrarlo
directamente con ``add_api_route``. ``get_v5_router`` se conserva para
compatibilidad, pero respeta el mismo feature flag opt-in.
"""
from __future__ import annotations

import asyncio
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db, ActivoPortafolio, TransaccionHistorial
from services.auth import get_usuario_actual, suscripcion_activa
from services.bvc import obtener_datos_bvc, obtener_tasa_bcv, _to_float, mercado_abierto
from services.feature_flags import portfolio_ibc_benchmark_v5_enabled
from services.fx_history_v5 import get_close_rate
from services.ibc_history_v5 import load_ibc_history
from services.portfolio_benchmark_v5 import compare_open_portfolio_to_ibc, normalize_ibc_points
from services.portfolio_snapshot_v5 import save_daily_snapshot, load_snapshots
from services.portfolio_performance_v5 import analyze_snapshot_performance

V5_BENCHMARK_PATH = "/api/v5/portfolio-benchmark"


def _tx_dict(tx: TransaccionHistorial) -> dict:
    raw_date = getattr(tx, "fecha", None)
    day = raw_date.date().isoformat() if hasattr(raw_date, "date") else str(raw_date or "")[:10]
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


def _terminal_ibc_point(points: list[tuple[date, float]], target: date) -> tuple[date, float] | None:
    best = None
    for day, level in points:
        if day > target:
            break
        best = (day, level)
    return best


def snapshot_capture_policy(*, valuation_day: date, ibc_day: date | None, market_is_open: bool) -> dict:
    """Decide si una observación puede convertirse en snapshot diario comparable."""
    if market_is_open:
        return {"capture": False, "reason": "market_intraday", "as_of": None}
    if ibc_day is None:
        return {"capture": False, "reason": "ibc_terminal_missing", "as_of": None}
    if ibc_day != valuation_day:
        return {
            "capture": False,
            "reason": "terminal_date_mismatch",
            "as_of": None,
            "valuation_as_of": valuation_day.isoformat(),
            "ibc_as_of": ibc_day.isoformat(),
        }
    return {"capture": True, "reason": None, "as_of": valuation_day.isoformat()}


async def portfolio_benchmark_v5(request: Request, db: Session = Depends(get_db)):
    # Defensa adicional: aunque el handler sea invocado directamente, el feature
    # sigue siendo opt-in y no debe generar snapshots con el flag apagado.
    if not portfolio_ibc_benchmark_v5_enabled():
        return JSONResponse({"error": "Benchmark V5 deshabilitado"}, status_code=404)

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

    valuation_day = date.today()
    ibc_raw, ibc_meta = _audited_ibc_points()
    normalized_ibc = normalize_ibc_points(ibc_raw)
    terminal_ibc = _terminal_ibc_point(normalized_ibc, valuation_day)
    current_ibc_day = terminal_ibc[0] if terminal_ibc else None
    current_ibc = terminal_ibc[1] if terminal_ibc else None

    open_benchmark = compare_open_portfolio_to_ibc(
        positions,
        transactions,
        ibc_raw,
        current_ibc=current_ibc,
        current_fx=current_fx if current_fx > 0 else None,
    )
    open_benchmark = dict(open_benchmark)
    open_benchmark["valuation_as_of"] = valuation_day.isoformat()
    open_benchmark["ibc_as_of"] = current_ibc_day.isoformat() if current_ibc_day else None
    open_benchmark["terminal_dates_aligned"] = bool(current_ibc_day == valuation_day)

    capture = snapshot_capture_policy(
        valuation_day=valuation_day,
        ibc_day=current_ibc_day,
        market_is_open=mercado_abierto(),
    )
    if capture["capture"]:
        try:
            snapshot_state = save_daily_snapshot(
                usuario.id,
                prices=prices,
                fx_bcv=current_fx if current_fx > 0 else None,
                ibc_level=current_ibc,
                as_of=valuation_day,
                source="market_close_aligned",
            )
        except Exception as exc:
            snapshot_state = {"saved": False, "error": type(exc).__name__}
    else:
        snapshot_state = {"saved": False, **capture}

    snapshots = load_snapshots(usuario.id)
    temporal = analyze_snapshot_performance(snapshots, transactions, ibc_points=ibc_raw)

    return JSONResponse({
        "engine_version": "v5-portfolio-benchmark",
        "as_of": valuation_day.isoformat(),
        "benchmark": open_benchmark,
        "performance": temporal,
        "ibc": ibc_meta,
        "snapshot": snapshot_state,
        "fx_current": current_fx if current_fx > 0 else None,
        "notes": [
            "Benchmark abierto: lotes FIFO y fechas equivalentes contra IBC.",
            "USD usa BCV histórico por fecha; si falta, no se aproxima.",
            "Snapshots temporales sólo se guardan con mercado cerrado e IBC del mismo día.",
            "Ventanas 1M/3M/6M/YTD/1Y: Modified Dietz y benchmark IBC con los mismos flujos.",
        ],
    })


def get_v5_router() -> APIRouter:
    """Router de compatibilidad; se construye según el flag en cada llamada."""
    router = APIRouter()
    if portfolio_ibc_benchmark_v5_enabled():
        router.add_api_route(
            V5_BENCHMARK_PATH,
            portfolio_benchmark_v5,
            methods=["GET"],
            response_class=JSONResponse,
        )
    return router
