"""ISLR calculator route extracted from legacy main.py without behavior changes."""
from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import ActivoPortafolio, get_db
from services.auth import dias_restantes, get_usuario_actual
from services.bvc import _to_float, mercado_abierto, obtener_datos_bvc


async def islr_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    datos_bolsa = await obtener_datos_bvc()
    activos = db.query(ActivoPortafolio).filter(ActivoPortafolio.usuario_id == usuario.id).all()
    mapa = {i["COD_SIMB"]: _to_float(i.get("PRECIO")) for i in datos_bolsa}
    ganancia = sum(
        (mapa.get(a.simbolo, a.precio_promedio) - a.precio_promedio) * a.cantidad
        for a in activos
    )
    return render("islr.html", {
        "request": request, "usuario": usuario,
        "ganancia_portafolio": max(0, ganancia),
        "ut_actual": 9600,
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(), "active": "",
    })


def register_islr_routes(app: FastAPI) -> None:
    app.add_api_route("/islr", islr_page, methods=["GET"], response_class=HTMLResponse)
