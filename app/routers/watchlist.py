"""Watchlist handlers extracted from legacy main.py without behavior changes."""
from __future__ import annotations

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import Watchlist, get_db
from services.auth import dias_restantes, get_usuario_actual
from services.bvc import mercado_abierto, obtener_datos_bvc


async def ver_watchlist(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    simbolos_wl = [w.simbolo for w in usuario.watchlist]
    datos_bolsa = await obtener_datos_bvc()
    items = [i for i in datos_bolsa if i.get("COD_SIMB") in simbolos_wl]
    return render("watchlist.html", {
        "request": request,
        "usuario": usuario,
        "items": items,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(),
        "active": "",
    })


async def agregar_watchlist(request: Request, simbolo: str = Form(...), db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"ok": False}, status_code=401)
    existe = db.query(Watchlist).filter(
        Watchlist.usuario_id == usuario.id,
        Watchlist.simbolo == simbolo.upper(),
    ).first()
    if not existe:
        db.add(Watchlist(usuario_id=usuario.id, simbolo=simbolo.upper()))
        db.commit()
    return JSONResponse({"ok": True})


async def eliminar_watchlist(request: Request, simbolo: str = Form(...), db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    item = db.query(Watchlist).filter(
        Watchlist.usuario_id == usuario.id,
        Watchlist.simbolo == simbolo.upper(),
    ).first()
    if item:
        db.delete(item)
        db.commit()
    ref = request.headers.get("referer", "/watchlist")
    return RedirectResponse(url=ref, status_code=303)


def register_watchlist_routes(app: FastAPI) -> None:
    app.add_api_route("/watchlist", ver_watchlist, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/watchlist/agregar", agregar_watchlist, methods=["POST"])
    app.add_api_route("/watchlist/eliminar", eliminar_watchlist, methods=["POST"])
