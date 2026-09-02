"""Portfolio V4 handlers extracted from legacy main.py without behavior changes."""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import ActivoPortafolio, get_db
from services.auth import dias_restantes, get_usuario_actual, suscripcion_activa
from services.bvc import _to_float, mercado_abierto, obtener_datos_bvc, obtener_tasa_bcv
from services.portafolio import calcular_fila, resumen_portafolio


async def ver_portafolio(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    if not suscripcion_activa(usuario):
        return RedirectResponse(url="/suscripcion", status_code=302)

    datos_bolsa = await obtener_datos_bvc()
    tasa_auto = await obtener_tasa_bcv()
    config_tasa = tasa_auto if tasa_auto > 0 else float(os.environ.get("TASA_BCV", "0"))

    activos_db = db.query(ActivoPortafolio).filter(ActivoPortafolio.usuario_id == usuario.id).all()
    portafolio = {
        a.simbolo: {
            "cantidad": a.cantidad,
            "precio_promedio": a.precio_promedio,
            "comision": a.comision,
            "registro": a.registro,
            "iva": a.iva,
        }
        for a in activos_db
    }

    mapa_precios = {item["COD_SIMB"]: _to_float(item.get("PRECIO") or 0) for item in datos_bolsa}
    total_mkt = sum(
        _to_float(d.get("cantidad")) * mapa_precios.get(simb, _to_float(d.get("precio_promedio")))
        for simb, d in portafolio.items()
    )

    filas = [
        calcular_fila(
            simb,
            d,
            mapa_precios.get(simb, _to_float(d.get("precio_promedio"))),
            total_mkt,
            config_tasa,
        )
        for simb, d in portafolio.items()
    ]
    resumen = resumen_portafolio(portafolio, datos_bolsa, config_tasa)

    return render("portafolio.html", {
        "request": request,
        "filas": filas,
        "resumen": resumen,
        "tasa": config_tasa,
        "labels": [f["simb"] for f in filas],
        "valores": [round(f["val_mkt"], 2) for f in filas],
        "ganancias": [round(f["ganancia"], 2) for f in filas],
        "active": "portafolio",
        "usuario": usuario,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(),
    })


async def configurar(tasa: float = Form(...), request: Request = None, db: Session = Depends(get_db)):
    os.environ["TASA_BCV"] = str(tasa)
    return RedirectResponse(url="/portafolio", status_code=303)


async def agregar(
    request: Request,
    simb: str = Form(...),
    cant: float = Form(...),
    precio: float = Form(...),
    com: float = Form(0),
    reg: float = Form(0),
    iva: float = Form(16),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    existente = db.query(ActivoPortafolio).filter(
        ActivoPortafolio.usuario_id == usuario.id,
        ActivoPortafolio.simbolo == simb.upper(),
    ).first()
    if existente:
        cant_total = existente.cantidad + cant
        precio_prom = ((existente.precio_promedio * existente.cantidad) + (precio * cant)) / cant_total
        existente.cantidad = cant_total
        existente.precio_promedio = round(precio_prom, 2)
        existente.comision = existente.comision + com
        existente.registro = existente.registro + reg
    else:
        db.add(ActivoPortafolio(
            usuario_id=usuario.id,
            simbolo=simb.upper(),
            cantidad=cant,
            precio_promedio=precio,
            comision=com,
            registro=reg,
            iva=iva,
        ))
    db.commit()
    return RedirectResponse(url="/portafolio", status_code=303)


async def editar(
    request: Request,
    simb: str = Form(...),
    cant: float = Form(...),
    precio: float = Form(...),
    com: float = Form(0),
    reg: float = Form(0),
    iva: float = Form(16),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    activo = db.query(ActivoPortafolio).filter(
        ActivoPortafolio.usuario_id == usuario.id,
        ActivoPortafolio.simbolo == simb.upper(),
    ).first()
    if activo:
        activo.cantidad = cant
        activo.precio_promedio = precio
        activo.comision = com
        activo.registro = reg
        activo.iva = iva
        db.commit()
    return RedirectResponse(url="/portafolio", status_code=303)


async def eliminar(request: Request, simb: str = Form(...), db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    activo = db.query(ActivoPortafolio).filter(
        ActivoPortafolio.usuario_id == usuario.id,
        ActivoPortafolio.simbolo == simb.upper(),
    ).first()
    if activo:
        db.delete(activo)
        db.commit()
    return RedirectResponse(url="/portafolio", status_code=303)


def register_portfolio_routes(app: FastAPI) -> None:
    app.add_api_route("/portafolio", ver_portafolio, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/configurar", configurar, methods=["POST"])
    app.add_api_route("/agregar", agregar, methods=["POST"])
    app.add_api_route("/editar", editar, methods=["POST"])
    app.add_api_route("/eliminar", eliminar, methods=["POST"])
