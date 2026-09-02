"""Portfolio import handlers extracted from legacy main.py without behavior changes."""
from __future__ import annotations

import json

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import ActivoPortafolio, get_db
from services.auth import dias_restantes, get_usuario_actual
from services.bvc import mercado_abierto
from services.importador import importar_archivo


async def importar_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    return render("importar.html", {
        "request": request,
        "usuario": usuario,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(),
        "active": "",
        "error": None,
        "activos_preview": None,
        "activos_json": None,
    })


async def importar_post(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    form = await request.form()
    archivo = form.get("archivo")
    if not archivo or not archivo.filename:
        return render("importar.html", {
            "request": request,
            "usuario": usuario,
            "dias": dias_restantes(usuario),
            "mercado": mercado_abierto(),
            "active": "",
            "error": "Selecciona un archivo",
            "activos_preview": None,
            "activos_json": None,
        })
    try:
        contenido = await archivo.read()
        activos = importar_archivo(contenido, archivo.filename)
        if not activos:
            raise ValueError("No se encontraron activos en el archivo")
        return render("importar.html", {
            "request": request,
            "usuario": usuario,
            "dias": dias_restantes(usuario),
            "mercado": mercado_abierto(),
            "active": "",
            "error": None,
            "activos_preview": activos,
            "activos_json": json.dumps(activos),
        })
    except Exception as exc:
        return render("importar.html", {
            "request": request,
            "usuario": usuario,
            "dias": dias_restantes(usuario),
            "mercado": mercado_abierto(),
            "active": "",
            "error": str(exc),
            "activos_preview": None,
            "activos_json": None,
        })


async def importar_confirmar(request: Request, datos: str = Form(...), db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    activos = json.loads(datos)
    for a in activos:
        existente = db.query(ActivoPortafolio).filter(
            ActivoPortafolio.usuario_id == usuario.id,
            ActivoPortafolio.simbolo == a["simbolo"],
        ).first()
        if existente:
            existente.cantidad = a["cantidad"]
            existente.precio_promedio = a["precio_promedio"]
        else:
            db.add(ActivoPortafolio(
                usuario_id=usuario.id,
                simbolo=a["simbolo"],
                cantidad=a["cantidad"],
                precio_promedio=a["precio_promedio"],
                comision=a.get("comision", 0),
                registro=a.get("registro", 0),
                iva=a.get("iva", 16),
            ))
    db.commit()
    return RedirectResponse(url="/portafolio", status_code=303)


def register_portfolio_import_routes(app: FastAPI) -> None:
    app.add_api_route("/portafolio/importar", importar_page, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/portafolio/importar", importar_post, methods=["POST"], response_class=HTMLResponse)
    app.add_api_route("/portafolio/importar/confirmar", importar_confirmar, methods=["POST"])
