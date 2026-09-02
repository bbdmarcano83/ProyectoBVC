"""Transaction history routes extracted from legacy main.py without behavior changes."""
from __future__ import annotations

from datetime import datetime

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import TransaccionHistorial, get_db
from services.auth import dias_restantes, get_usuario_actual
from services.bvc import mercado_abierto, obtener_datos_bvc


async def ver_historial(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    txs = db.query(TransaccionHistorial).filter(
        TransaccionHistorial.usuario_id == usuario.id
    ).order_by(TransaccionHistorial.fecha.desc()).all()
    datos_bolsa = await obtener_datos_bvc()
    simbolos = sorted([i["COD_SIMB"] for i in datos_bolsa])
    compras = sum(1 for t in txs if t.tipo == "compra")
    ventas = sum(1 for t in txs if t.tipo == "venta")
    ganancia_total = sum(
        t.cantidad * t.precio if t.tipo == "venta" else -(t.cantidad * t.precio)
        for t in txs
    )
    return render("historial.html", {
        "request": request, "usuario": usuario,
        "transacciones": txs, "simbolos": simbolos,
        "compras": compras, "ventas": ventas,
        "ganancia_total": ganancia_total,
        "hoy": datetime.now().strftime("%Y-%m-%d"),
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(), "active": "",
    })


async def agregar_historial(
    request: Request,
    simbolo: str = Form(...), tipo: str = Form(...),
    fecha: str = Form(...), cantidad: float = Form(...),
    precio: float = Form(...), comision: float = Form(0),
    notas: str = Form(""),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
    db.add(TransaccionHistorial(
        usuario_id=usuario.id, simbolo=simbolo.upper(), tipo=tipo,
        cantidad=cantidad, precio=precio, comision=comision,
        notas=notas, fecha=fecha_dt,
    ))
    db.commit()
    return RedirectResponse(url="/historial", status_code=303)


async def eliminar_historial(request: Request, tx_id: int = Form(...), db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    tx = db.query(TransaccionHistorial).filter(
        TransaccionHistorial.id == tx_id,
        TransaccionHistorial.usuario_id == usuario.id
    ).first()
    if tx:
        db.delete(tx)
        db.commit()
    return RedirectResponse(url="/historial", status_code=303)


def register_history_routes(app: FastAPI) -> None:
    app.add_api_route("/historial", ver_historial, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/historial/agregar", agregar_historial, methods=["POST"])
    app.add_api_route("/historial/eliminar", eliminar_historial, methods=["POST"])
