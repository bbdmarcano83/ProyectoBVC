"""Legacy Telegram and price-alert routes, preserving duplicate registration order."""
from __future__ import annotations

import os
import random
import string

import httpx
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import AlertaPrecio, Usuario as UsuarioModel, get_db
from services.auth import dias_restantes, get_usuario_actual
from services.bvc import mercado_abierto, obtener_datos_bvc
from services.telegram import TELEGRAM_API, enviar_mensaje, verificar_codigo


async def _vincular_telegram(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    codigo = "".join(random.choices(string.digits, k=6))
    usuario.telegram_codigo = codigo
    db.commit()
    return JSONResponse({"codigo": codigo, "bot": "@CaracasBullBot"})


async def _webhook_telegram_primary(request: Request, db: Session = Depends(get_db)):
    datos = await request.json()
    mensaje = datos.get("message", {})
    chat_id = str(mensaje.get("chat", {}).get("id", ""))
    texto = mensaje.get("text", "").strip()

    if not chat_id:
        return JSONResponse({"ok": True})

    if texto.startswith("/start "):
        codigo = texto.replace("/start ", "").strip()
        await verificar_codigo(chat_id, codigo, db)
    elif texto == "/start":
        msg = "Bienvenido a CaracasBull. Ve a tu perfil y haz clic en Vincular Telegram."
        await enviar_mensaje(chat_id, msg)
    elif texto == "/status":
        u = db.query(UsuarioModel).filter(UsuarioModel.telegram_chat_id == chat_id).first()
        if u:
            plan = u.suscripcion.plan if u.suscripcion else "trial"
            await enviar_mensaje(chat_id, f"Cuenta vinculada: {u.nombre} | Plan: {plan}")
        else:
            await enviar_mensaje(chat_id, "No hay cuenta vinculada a este chat.")

    return JSONResponse({"ok": True})


async def _webhook_telegram_secondary(request: Request, db: Session = Depends(get_db)):
    datos = await request.json()
    mensaje = datos.get("message", {})
    chat_id = str(mensaje.get("chat", {}).get("id", ""))
    texto = mensaje.get("text", "").strip()
    if not chat_id:
        return JSONResponse({"ok": True})
    if texto.startswith("/start "):
        codigo = texto.replace("/start ", "").strip()
        await verificar_codigo(chat_id, codigo, db)
    elif texto == "/start":
        bienvenida = "Bienvenido a CaracasBull. Ve a tu perfil y haz clic en Vincular Telegram."
        await enviar_mensaje(chat_id, bienvenida)
    elif texto == "/status":
        u = db.query(UsuarioModel).filter(UsuarioModel.telegram_chat_id == chat_id).first()
        if u:
            plan = u.suscripcion.plan if u.suscripcion else "trial"
            await enviar_mensaje(chat_id, f"Cuenta vinculada: {u.nombre} | Plan: {plan}")
        else:
            await enviar_mensaje(chat_id, "No hay cuenta vinculada a este chat.")
    return JSONResponse({"ok": True})


async def _ver_alertas(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    alertas = db.query(AlertaPrecio).filter(
        AlertaPrecio.usuario_id == usuario.id
    ).order_by(AlertaPrecio.creado_en.desc()).all()
    datos_bolsa = await obtener_datos_bvc()
    simbolos = sorted([item["COD_SIMB"] for item in datos_bolsa])
    return render("alertas.html", {
        "request": request, "usuario": usuario,
        "alertas": alertas, "simbolos": simbolos,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(), "active": "",
    })


async def _crear_alerta(
    request: Request,
    simbolo: str = Form(...),
    tipo: str = Form(...),
    porcentaje: float = Form(...),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    db.add(AlertaPrecio(
        usuario_id=usuario.id,
        simbolo=simbolo.upper(),
        tipo=tipo,
        porcentaje=porcentaje,
        activa=True,
        disparada=False,
    ))
    db.commit()
    return RedirectResponse(url="/alertas", status_code=303)


async def _eliminar_alerta(
    request: Request,
    alerta_id: int = Form(...),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    alerta = db.query(AlertaPrecio).filter(
        AlertaPrecio.id == alerta_id,
        AlertaPrecio.usuario_id == usuario.id,
    ).first()
    if alerta:
        db.delete(alerta)
        db.commit()
    return RedirectResponse(url="/alertas", status_code=303)


async def _reset_alerta(
    request: Request,
    alerta_id: int = Form(...),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    alerta = db.query(AlertaPrecio).filter(
        AlertaPrecio.id == alerta_id,
        AlertaPrecio.usuario_id == usuario.id,
    ).first()
    if alerta:
        alerta.disparada = False
        db.commit()
    return RedirectResponse(url="/alertas", status_code=303)


def _register_alert_set(app: FastAPI) -> None:
    app.add_api_route("/alertas", _ver_alertas, methods=["GET"], response_class=HTMLResponse, name="ver_alertas")
    app.add_api_route("/alertas/crear", _crear_alerta, methods=["POST"], name="crear_alerta")
    app.add_api_route("/alertas/eliminar", _eliminar_alerta, methods=["POST"], name="eliminar_alerta")
    app.add_api_route("/alertas/reset", _reset_alerta, methods=["POST"], name="reset_alerta")


def register_legacy_notification_routes(app: FastAPI) -> None:
    app.add_api_route("/telegram/vincular", _vincular_telegram, methods=["POST"], name="vincular_telegram")
    app.add_api_route("/webhook/telegram", _webhook_telegram_primary, methods=["POST"], name="webhook_telegram")
    _register_alert_set(app)
    app.add_api_route("/telegram/vincular", _vincular_telegram, methods=["POST"], name="vincular_telegram")
    app.add_api_route("/webhook/telegram", _webhook_telegram_secondary, methods=["POST"], name="webhook_telegram")
    _register_alert_set(app)


async def registrar_webhook_telegram():
    """Registra el webhook de Telegram al arrancar la app."""
    app_url = os.environ.get("APP_URL", "")
    if not app_url:
        return
    webhook_url = f"{app_url}/webhook/telegram"
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(f"{TELEGRAM_API}/setWebhook", json={"url": webhook_url})
            if r.status_code == 200:
                print(f"[Telegram] Webhook registrado: {webhook_url}")
        except Exception as e:
            print(f"[Telegram] Error registrando webhook: {e}")
