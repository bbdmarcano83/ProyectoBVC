"""Portfolio handlers with weighted-average position management and transaction ledger sync."""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import ActivoPortafolio, TransaccionHistorial, get_db
from services.auth import dias_restantes, get_usuario_actual, suscripcion_activa
from services.bvc import _to_float, mercado_abierto, obtener_datos_bvc, obtener_tasa_bcv
from services.portafolio import calcular_fila, resumen_portafolio


def _fee_total(comision: float, registro: float, iva_pct: float) -> float:
    comision = max(_to_float(comision), 0.0)
    registro = max(_to_float(registro), 0.0)
    iva_pct = max(_to_float(iva_pct), 0.0)
    return comision + registro + (comision * iva_pct / 100.0)


def _normalizar_simbolo(simb: str) -> str:
    return (simb or "").strip().upper()


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
    """Compra/suma una posición y recalcula el costo promedio ponderado."""
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)

    simbolo = _normalizar_simbolo(simb)
    cant = _to_float(cant)
    precio = _to_float(precio)
    if not simbolo or cant <= 0 or precio <= 0:
        return RedirectResponse(url="/portafolio?error=compra-invalida", status_code=303)

    existente = db.query(ActivoPortafolio).filter(
        ActivoPortafolio.usuario_id == usuario.id,
        ActivoPortafolio.simbolo == simbolo,
    ).first()

    if existente:
        cantidad_anterior = _to_float(existente.cantidad)
        cantidad_total = cantidad_anterior + cant
        costo_anterior = _to_float(existente.precio_promedio) * cantidad_anterior
        costo_nuevo = precio * cant
        existente.cantidad = cantidad_total
        existente.precio_promedio = round((costo_anterior + costo_nuevo) / cantidad_total, 6)
        existente.comision = _to_float(existente.comision) + max(_to_float(com), 0.0)
        existente.registro = _to_float(existente.registro) + max(_to_float(reg), 0.0)
        existente.iva = _to_float(iva)
    else:
        db.add(ActivoPortafolio(
            usuario_id=usuario.id,
            simbolo=simbolo,
            cantidad=cant,
            precio_promedio=precio,
            comision=max(_to_float(com), 0.0),
            registro=max(_to_float(reg), 0.0),
            iva=max(_to_float(iva), 0.0),
        ))

    fee_total = _fee_total(com, reg, iva)
    tasa_bcv = await obtener_tasa_bcv()
    db.add(TransaccionHistorial(
        usuario_id=usuario.id,
        simbolo=simbolo,
        tipo="compra",
        cantidad=cant,
        precio=precio,
        comision=max(_to_float(com), 0.0),
        registro=max(_to_float(reg), 0.0),
        iva=max(_to_float(iva), 0.0),
        motivo="portafolio_compra",
        notas="Compra/suma registrada desde Portafolio",
        tasa_bcv=tasa_bcv if tasa_bcv > 0 else None,
        fee_total=fee_total,
        neto=(cant * precio) + fee_total,
    ))
    db.commit()
    return RedirectResponse(url="/portafolio", status_code=303)


async def reducir(
    request: Request,
    simb: str = Form(...),
    cant: float = Form(...),
    precio: float = Form(...),
    com: float = Form(0),
    reg: float = Form(0),
    iva: float = Form(16),
    db: Session = Depends(get_db),
):
    """Vende/reduce una posición manteniendo el costo promedio de lo que permanece."""
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)

    simbolo = _normalizar_simbolo(simb)
    cant = _to_float(cant)
    precio = _to_float(precio)
    activo = db.query(ActivoPortafolio).filter(
        ActivoPortafolio.usuario_id == usuario.id,
        ActivoPortafolio.simbolo == simbolo,
    ).first()
    if not activo or cant <= 0 or precio <= 0 or cant > _to_float(activo.cantidad):
        return RedirectResponse(url="/portafolio?error=venta-invalida", status_code=303)

    cantidad_anterior = _to_float(activo.cantidad)
    cantidad_restante = cantidad_anterior - cant
    proporcion_restante = (cantidad_restante / cantidad_anterior) if cantidad_anterior > 0 else 0.0

    if cantidad_restante > 1e-12:
        activo.cantidad = cantidad_restante
        # El costo promedio por título no cambia al vender una parte de la posición.
        activo.comision = _to_float(activo.comision) * proporcion_restante
        activo.registro = _to_float(activo.registro) * proporcion_restante
    else:
        db.delete(activo)

    fee_total = _fee_total(com, reg, iva)
    tasa_bcv = await obtener_tasa_bcv()
    db.add(TransaccionHistorial(
        usuario_id=usuario.id,
        simbolo=simbolo,
        tipo="venta",
        cantidad=cant,
        precio=precio,
        comision=max(_to_float(com), 0.0),
        registro=max(_to_float(reg), 0.0),
        iva=max(_to_float(iva), 0.0),
        motivo="portafolio_venta",
        notas="Venta/reducción registrada desde Portafolio",
        tasa_bcv=tasa_bcv if tasa_bcv > 0 else None,
        fee_total=fee_total,
        neto=(cant * precio) - fee_total,
    ))
    db.commit()
    return RedirectResponse(url="/portafolio", status_code=303)


async def editar(
    request: Request,
    simb: str = Form(...),
    cant: float = Form(...),
    precio: float = Form(...),
    db: Session = Depends(get_db),
):
    """Corrige cantidad/costo promedio sin borrar los gastos acumulados ni simular una operación."""
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    simbolo = _normalizar_simbolo(simb)
    activo = db.query(ActivoPortafolio).filter(
        ActivoPortafolio.usuario_id == usuario.id,
        ActivoPortafolio.simbolo == simbolo,
    ).first()
    if activo and _to_float(cant) >= 0 and _to_float(precio) >= 0:
        activo.cantidad = _to_float(cant)
        activo.precio_promedio = _to_float(precio)
        # Comisión, registro e IVA se preservan. Corregir no es una compra/venta.
        db.commit()
    return RedirectResponse(url="/portafolio", status_code=303)


async def eliminar(request: Request, simb: str = Form(...), db: Session = Depends(get_db)):
    """Borrado administrativo completo de posición e historial del símbolo."""
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    simbolo = _normalizar_simbolo(simb)
    activo = db.query(ActivoPortafolio).filter(
        ActivoPortafolio.usuario_id == usuario.id,
        ActivoPortafolio.simbolo == simbolo,
    ).first()
    if activo:
        db.delete(activo)
    db.query(TransaccionHistorial).filter(
        TransaccionHistorial.usuario_id == usuario.id,
        TransaccionHistorial.simbolo == simbolo,
    ).delete(synchronize_session=False)
    db.commit()
    return RedirectResponse(url="/portafolio", status_code=303)


def register_portfolio_routes(app: FastAPI) -> None:
    app.add_api_route("/portafolio", ver_portafolio, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/configurar", configurar, methods=["POST"])
    app.add_api_route("/agregar", agregar, methods=["POST"])
    app.add_api_route("/reducir", reducir, methods=["POST"])
    app.add_api_route("/editar", editar, methods=["POST"])
    app.add_api_route("/eliminar", eliminar, methods=["POST"])
