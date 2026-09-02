"""Public home and BVC board handlers extracted from legacy main.py."""
from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import get_db
from services.auth import dias_restantes, get_usuario_actual, suscripcion_activa
from services.bvc import mercado_abierto, obtener_datos_bvc


async def index(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    return render("landing.html", {"request": request, "usuario": usuario})


async def pizarra(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/", status_code=302)
    if not suscripcion_activa(usuario):
        return RedirectResponse(url="/suscripcion", status_code=302)

    datos = await obtener_datos_bvc()
    return render("pizarra.html", {
        "request": request,
        "datos": datos,
        "active": "pizarra",
        "usuario": usuario,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(),
    })


def register_market_routes(app: FastAPI) -> None:
    app.add_api_route("/", index, methods=["GET", "HEAD"], response_class=HTMLResponse)
    app.add_api_route("/pizarra", pizarra, methods=["GET"], response_class=HTMLResponse)
