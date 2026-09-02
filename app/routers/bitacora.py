"""Bitácora handlers extracted from legacy main.py without behavior changes."""
from __future__ import annotations

from datetime import datetime

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import TransaccionHistorial, get_db
from services.auth import dias_restantes, get_usuario_actual, suscripcion_activa
from services.bvc import mercado_abierto, obtener_tasa_bcv


async def ver_bitacora(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    if not suscripcion_activa(usuario):
        return RedirectResponse(url="/suscripcion", status_code=302)

    transacciones = db.query(TransaccionHistorial).filter(
        TransaccionHistorial.usuario_id == usuario.id
    ).order_by(TransaccionHistorial.fecha.desc()).all()

    compras = sum(1 for t in transacciones if t.tipo == "compra")
    ventas = sum(1 for t in transacciones if t.tipo == "venta")
    total_fees = sum(t.fee_total or 0 for t in transacciones)
    total_bruto = sum((t.cantidad or 0) * (t.precio or 0) for t in transacciones)
    fee_pct = round((total_fees / total_bruto * 100), 2) if total_bruto > 0 else 0

    tasa_bcv = await obtener_tasa_bcv()

    return render("bitacora.html", {
        "request": request,
        "transacciones": transacciones,
        "compras": compras,
        "ventas": ventas,
        "total_fees": total_fees,
        "fee_pct": fee_pct,
        "tasa_bcv": tasa_bcv,
        "active": "bitacora",
        "usuario": usuario,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(),
    })


async def crear_entrada_bitacora(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    data = await request.json()
    simbolo = data.get("simbolo", "").upper().strip()
    tipo = data.get("tipo", "compra")
    cantidad = float(data.get("cantidad", 0))
    precio = float(data.get("precio", 0))
    motivo = data.get("motivo", "")
    notas = data.get("notas", "")
    fecha_str = data.get("fecha", "")

    if not simbolo or cantidad <= 0 or precio <= 0:
        return JSONResponse({"detail": "Datos incompletos"}, status_code=400)

    if fecha_str:
        try:
            fecha_dt = datetime.strptime(fecha_str, "%Y-%m-%d")
        except ValueError:
            fecha_dt = datetime.now()
    else:
        fecha_dt = datetime.now()

    bruto = cantidad * precio
    corretaje = bruto * 0.04
    iva = corretaje * 0.16
    islr = bruto * 0.01 if tipo == "venta" else 0
    registro = bruto * 0.001
    fee_total = corretaje + iva + islr + registro
    neto = bruto - fee_total if tipo == "venta" else bruto + fee_total

    tasa_bcv = await obtener_tasa_bcv()

    nueva = TransaccionHistorial(
        usuario_id=usuario.id,
        simbolo=simbolo,
        tipo=tipo,
        cantidad=cantidad,
        precio=precio,
        comision=4.0,
        registro=0.1,
        iva=16,
        motivo=motivo,
        notas=notas,
        tasa_bcv=tasa_bcv,
        fee_total=fee_total,
        neto=neto,
        fecha=fecha_dt,
    )
    db.add(nueva)
    db.commit()
    return JSONResponse({"ok": True, "id": nueva.id})


async def eliminar_bitacora(tx_id: int, request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"error": "No autorizado"}, status_code=401)
    tx = db.query(TransaccionHistorial).filter(
        TransaccionHistorial.id == tx_id,
        TransaccionHistorial.usuario_id == usuario.id,
    ).first()
    if not tx:
        return JSONResponse({"detail": "No encontrado"}, status_code=404)
    db.delete(tx)
    db.commit()
    return JSONResponse({"ok": True})


def register_bitacora_routes(app: FastAPI) -> None:
    app.add_api_route("/bitacora", ver_bitacora, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/api/bitacora", crear_entrada_bitacora, methods=["POST"], response_class=JSONResponse)
    app.add_api_route("/api/bitacora/{tx_id}", eliminar_bitacora, methods=["DELETE"], response_class=JSONResponse)
