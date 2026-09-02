"""Subscription/payment handlers extracted from legacy main.py."""
from __future__ import annotations

import json

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import get_db
from services.auth import dias_restantes, get_usuario_actual, require_usuario, suscripcion_activa
from services.bvc import mercado_abierto
from services.pagos import crear_pago, procesar_webhook, verificar_estado_pago, verificar_firma_ipn


async def suscripcion_page(request: Request, mensaje: str = None, db: Session = Depends(get_db)):
    usuario = require_usuario(request, db)
    if isinstance(usuario, RedirectResponse):
        return usuario
    return render("suscripcion.html", {
        "request": request,
        "usuario": usuario,
        "activa": suscripcion_activa(usuario),
        "dias": dias_restantes(usuario),
        "pago": None,
        "mensaje": mensaje,
        "active": "",
        "mercado": mercado_abierto(),
    })


async def suscripcion_pagar(
    request: Request,
    plan: str = Form(...),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    pago = await crear_pago(usuario.id, plan, usuario.email)
    mensaje_error = None
    if not pago:
        mensaje_error = "Error al conectar con el sistema de pagos. Verifica que NOWPAYMENTS_API_KEY esté configurada en Render."
    return render("suscripcion.html", {
        "request": request,
        "usuario": usuario,
        "activa": suscripcion_activa(usuario),
        "dias": dias_restantes(usuario),
        "pago": pago,
        "mensaje": mensaje_error,
        "active": "",
        "mercado": mercado_abierto(),
    })


async def estado_pago(payment_id: str):
    datos = await verificar_estado_pago(payment_id)
    if datos:
        return JSONResponse({"status": datos.get("payment_status", "waiting")})
    return JSONResponse({"status": "waiting"})


async def suscripcion_exitosa(request: Request, db: Session = Depends(get_db)):
    return RedirectResponse(url="/suscripcion?mensaje=¡Pago recibido! Tu suscripción será activada en minutos.", status_code=302)


async def webhook_nowpayments(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    firma = request.headers.get("x-nowpayments-sig", "")
    if not verificar_firma_ipn(body, firma):
        return JSONResponse({"error": "firma inválida"}, status_code=400)
    datos = json.loads(body)
    procesar_webhook(db, datos)
    return JSONResponse({"ok": True})


def register_subscription_routes(app: FastAPI) -> None:
    app.add_api_route("/suscripcion", suscripcion_page, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/suscripcion/pagar", suscripcion_pagar, methods=["POST"])
    app.add_api_route("/suscripcion/estado/{payment_id}", estado_pago, methods=["GET"])
    app.add_api_route("/suscripcion/exitosa", suscripcion_exitosa, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/webhook/nowpayments", webhook_nowpayments, methods=["POST"])
