import sys
sys.setrecursionlimit(5000)
import uvicorn
import asyncio
import os
import json
import httpx

from fastapi import FastAPI, Form, Request, Depends, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from database import init_db, get_db, SessionLocal, AlertaPrecio, TransaccionHistorial
from services.alertas_worker import loop_alertas
from services.bvc import obtener_datos_bvc, obtener_detalle_profundo, obtener_historico, _to_float, formatear_bs, formatear_entero, formatear_millones, mercado_abierto, obtener_tasa_bcv
from services.portafolio import calcular_fila, resumen_portafolio
from services.auth import (
    crear_usuario, autenticar_usuario, crear_token,
    get_usuario_actual, require_usuario, require_suscripcion,
    suscripcion_activa, dias_restantes, hash_password, get_plan
)
from services.pagos import crear_pago, verificar_firma_ipn, procesar_webhook, verificar_estado_pago
from services.importador import importar_archivo
import httpx as httpx_client
from services.pdf_reporte import generar_reporte
from services.pdf_reporte import generar_reporte
from services.email import email_recuperar_password, email_bienvenida
from app.startup import run_startup
from app.factory import create_app
from app.templating import render
from app.routers.auth import register_auth_routes
from app.routers.subscription import register_subscription_routes
from app.routers.market import register_market_routes
from app.routers.bitacora import register_bitacora_routes
from app.routers.alerts import register_alert_routes
from app.routers.scoring import register_scoring_routes
from app.routers.profile import register_profile_routes
from app.routers.detail import register_detail_routes
from app.routers.api_misc import register_misc_api_routes
from app.routers.recovery import register_recovery_routes
from app.routers.portfolio import register_portfolio_routes
from app.routers.watchlist import register_watchlist_routes
from app.routers.admin import register_admin_routes
from app.routers.pwa import register_pwa_routes
from app.routers.portfolio_import import register_portfolio_import_routes
from app.routers.portfolio_pdf import register_portfolio_pdf_routes
from app.routers.report_pdf import register_report_pdf_routes
from app.routers.history import register_history_routes
from app.routers.comparator import register_comparator_routes
from app.routers.islr import register_islr_routes
from app.routers.index_market import register_index_market_routes
from database import ActivoPortafolio, Watchlist

app = create_app()

# ── Init DB al arrancar ────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    # `registrar_webhook_telegram` se resuelve al ejecutar startup, después de
    # que el módulo completo haya terminado de importarse.
    await run_startup(registrar_webhook_telegram)

# ── Auth / Suscripción ─────────────────────────────────────────────────────────
register_auth_routes(app)
register_subscription_routes(app)


# ── Inicio / Pizarra ───────────────────────────────────────────────────────────
register_market_routes(app)


# ── Scoring (Rotación Sectorial) ──────────────────────────────────────────────
register_scoring_routes(app)


# ── Alertas de cierre Telegram ────────────────────────────────────────────────
register_alert_routes(app)


# ── Bitácora ──────────────────────────────────────────────────────────────────
register_bitacora_routes(app)


# ── Portafolio ────────────────────────────────────────────────────────────────
register_portfolio_routes(app)


# ── Detalle ───────────────────────────────────────────────────────────────────
register_detail_routes(app)


# ── Perfil ───────────────────────────────────────────────────────────────────────
register_profile_routes(app)


# ── Telegram ─────────────────────────────────────────────────────────────────────

@app.post("/telegram/vincular")
async def vincular_telegram(request: Request, db: Session = Depends(get_db)):
    import random, string
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    # Generar código de 6 dígitos
    codigo = "".join(random.choices(string.digits, k=6))
    usuario.telegram_codigo = codigo
    db.commit()
    return JSONResponse({"codigo": codigo, "bot": "@CaracasBullBot"})


@app.post("/webhook/telegram")
async def webhook_telegram(request: Request, db: Session = Depends(get_db)):
    from services.telegram import verificar_codigo
    datos = await request.json()
    mensaje = datos.get("message", {})
    chat_id = str(mensaje.get("chat", {}).get("id", ""))
    texto   = mensaje.get("text", "").strip()

    if not chat_id:
        return JSONResponse({"ok": True})

    if texto.startswith("/start "):
        codigo = texto.replace("/start ", "").strip()
        await verificar_codigo(chat_id, codigo, db)
    elif texto == "/start":
        from services.telegram import enviar_mensaje
        msg = "Bienvenido a CaracasBull. Ve a tu perfil y haz clic en Vincular Telegram."
        await enviar_mensaje(chat_id, msg)
    elif texto == "/status":
        from services.telegram import enviar_mensaje
        from database import Usuario as UsuarioModel
        u = db.query(UsuarioModel).filter(UsuarioModel.telegram_chat_id == chat_id).first()
        if u:
            plan = u.suscripcion.plan if u.suscripcion else "trial"
            await enviar_mensaje(chat_id, f"Cuenta vinculada: {u.nombre} | Plan: {plan}")
        else:
            await enviar_mensaje(chat_id, "No hay cuenta vinculada a este chat.")

    return JSONResponse({"ok": True})


# ── Alertas ───────────────────────────────────────────────────────────────────────

@app.get("/alertas", response_class=HTMLResponse)
async def ver_alertas(request: Request, db: Session = Depends(get_db)):
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


@app.post("/alertas/crear")
async def crear_alerta(
    request: Request,
    simbolo:    str   = Form(...),
    tipo:       str   = Form(...),
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


@app.post("/alertas/eliminar")
async def eliminar_alerta(
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


@app.post("/alertas/reset")
async def reset_alerta(
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


# ── Telegram ─────────────────────────────────────────────────────────────────────

@app.post("/telegram/vincular")
async def vincular_telegram(request: Request, db: Session = Depends(get_db)):
    import random, string
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    codigo = "".join(random.choices(string.digits, k=6))
    usuario.telegram_codigo = codigo
    db.commit()
    return JSONResponse({"codigo": codigo, "bot": "@CaracasBullBot"})


@app.post("/webhook/telegram")
async def webhook_telegram(request: Request, db: Session = Depends(get_db)):
    from services.telegram import verificar_codigo, enviar_mensaje
    from database import Usuario as UsuarioModel
    datos = await request.json()
    mensaje = datos.get("message", {})
    chat_id = str(mensaje.get("chat", {}).get("id", ""))
    texto   = mensaje.get("text", "").strip()
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


# ── Alertas ───────────────────────────────────────────────────────────────────────

@app.get("/alertas", response_class=HTMLResponse)
async def ver_alertas(request: Request, db: Session = Depends(get_db)):
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


@app.post("/alertas/crear")
async def crear_alerta(
    request: Request,
    simbolo:    str   = Form(...),
    tipo:       str   = Form(...),
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


@app.post("/alertas/eliminar")
async def eliminar_alerta(
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


@app.post("/alertas/reset")
async def reset_alerta(
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


# ── API endpoints ────────────────────────────────────────────────────────────────
register_misc_api_routes(app)


# ── Recuperar contraseña ─────────────────────────────────────────────────────────
register_recovery_routes(app)


# ── Chat Asistente ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres el asistente virtual de Caracas Bull, una plataforma de INFORMACION y ANALISIS del mercado bursatil de Caracas (BVC).

IMPORTANTE:
- NO somos broker, NO realizamos operaciones bursatiles
- NO damos asesoria de inversion ni recomendaciones para comprar/vender
- Solo proporcionamos informacion y herramientas de analisis

Puedes ayudar con:
- Como usar las funciones de la app (pizarra, portafolio, alertas, watchlist, comparador, ISLR, historial)
- Informacion general sobre la BVC y como funciona
- Problemas tecnicos con la plataforma
- Dudas sobre pagos y suscripciones (planes: Basico 1.5 USDT/mes, Pro 2.99 USDT/mes lanzamiento)
- Como vincular Telegram para alertas
- Como importar portafolio desde Excel/CSV

Si el usuario tiene un problema urgente de pago o tecnico grave, dile que escribe "soporte" para notificar al equipo.

Responde siempre en español, de forma amigable y concisa. Maximo 3 parrafos."""


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    return render("chat.html", {
        "request": request, "usuario": usuario,
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(), "active": "",
    })


@app.post("/chat")
async def chat_api(request: Request, db: Session = Depends(get_db)):
    import os
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"error": "no autorizado"}, status_code=401)

    body = await request.json()
    messages = body.get("messages", [])
    necesita_soporte = body.get("necesita_soporte", False)

    respuesta = ""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        try:
            # Construir historial en formato Gemini
            gemini_messages = []
            for m in messages[-10:]:
                role = "user" if m["role"] == "user" else "model"
                gemini_messages.append({"role": role, "parts": [{"text": m["content"]}]})

            async with httpx_client.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                        "contents": gemini_messages,
                        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.7},
                    }
                )
                if r.status_code == 200:
                    respuesta = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    print(f"[Gemini] Error {r.status_code}: {r.text[:200]}")
                    respuesta = "Lo siento, tuve un problema técnico. Intenta de nuevo en un momento."
        except Exception as e:
            print(f"[Chat] Error: {e}")
            respuesta = "Lo siento, no puedo responder en este momento. Escribe 'soporte' para contactar al equipo."
    else:
        respuesta = "El asistente no está configurado. Por favor contacta al soporte en soporte@caracasbull.com"

    # Notificar por Telegram si necesita soporte humano
    soporte_notificado = False
    if necesita_soporte and usuario.telegram_chat_id:
        from services.telegram import enviar_mensaje, TELEGRAM_TOKEN
        import os
        # Notificar al admin
        admin_chat = os.environ.get("ADMIN_TELEGRAM_CHAT_ID", "")
        if admin_chat:
            from services.telegram import enviar_mensaje
            await enviar_mensaje(admin_chat,
                f"🆘 <b>Soporte requerido</b>\n"
                f"Usuario: <b>{usuario.nombre}</b> ({usuario.email})\n"
                f"Mensaje: {messages[-1]['content'] if messages else 'N/A'}"
            )
            soporte_notificado = True

    return JSONResponse({"respuesta": respuesta, "soporte_notificado": soporte_notificado})


# ── Reporte PDF ──────────────────────────────────────────────────────────────────
register_portfolio_pdf_routes(app)


# ── Watchlist ────────────────────────────────────────────────────────────────────
register_watchlist_routes(app)


# ── Importar portafolio ───────────────────────────────────────────────────────
register_portfolio_import_routes(app)


# ── Admin ─────────────────────────────────────────────────────────────────────
register_admin_routes(app)


# ── PWA ───────────────────────────────────────────────────────────────────────
register_pwa_routes(app)


# ── Chat Asistente ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres el asistente virtual de Caracas Bull, una plataforma de INFORMACION y ANALISIS del mercado bursatil de Caracas (BVC).

IMPORTANTE:
- NO somos broker, NO realizamos operaciones bursatiles
- NO damos asesoria de inversion ni recomendaciones para comprar/vender
- Solo proporcionamos informacion y herramientas de analisis

Puedes ayudar con:
- Como usar las funciones de la app (pizarra, portafolio, alertas, watchlist, comparador, ISLR, historial)
- Informacion general sobre la BVC y como funciona
- Problemas tecnicos con la plataforma
- Dudas sobre pagos y suscripciones (planes: Basico 1.5 USDT/mes, Pro 2.99 USDT/mes lanzamiento)
- Como vincular Telegram para alertas
- Como importar portafolio desde Excel/CSV

Si el usuario tiene un problema urgente de pago o tecnico grave, dile que escribe "soporte" para notificar al equipo.

Responde siempre en español, de forma amigable y concisa. Maximo 3 parrafos."""


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    return render("chat.html", {
        "request": request, "usuario": usuario,
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(), "active": "",
    })


@app.post("/chat")
async def chat_api(request: Request, db: Session = Depends(get_db)):
    import os
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"error": "no autorizado"}, status_code=401)

    body = await request.json()
    messages = body.get("messages", [])
    necesita_soporte = body.get("necesita_soporte", False)

    respuesta = ""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        try:
            # Construir historial en formato Gemini
            gemini_messages = []
            for m in messages[-10:]:
                role = "user" if m["role"] == "user" else "model"
                gemini_messages.append({"role": role, "parts": [{"text": m["content"]}]})

            async with httpx_client.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                        "contents": gemini_messages,
                        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.7},
                    }
                )
                if r.status_code == 200:
                    respuesta = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    print(f"[Gemini] Error {r.status_code}: {r.text[:200]}")
                    respuesta = "Lo siento, tuve un problema técnico. Intenta de nuevo en un momento."
        except Exception as e:
            print(f"[Chat] Error: {e}")
            respuesta = "Lo siento, no puedo responder en este momento. Escribe 'soporte' para contactar al equipo."
    else:
        respuesta = "El asistente no está configurado. Por favor contacta al soporte en soporte@caracasbull.com"

    # Notificar por Telegram si necesita soporte humano
    soporte_notificado = False
    if necesita_soporte and usuario.telegram_chat_id:
        from services.telegram import enviar_mensaje, TELEGRAM_TOKEN
        import os
        # Notificar al admin
        admin_chat = os.environ.get("ADMIN_TELEGRAM_CHAT_ID", "")
        if admin_chat:
            from services.telegram import enviar_mensaje
            await enviar_mensaje(admin_chat,
                f"🆘 <b>Soporte requerido</b>\n"
                f"Usuario: <b>{usuario.nombre}</b> ({usuario.email})\n"
                f"Mensaje: {messages[-1]['content'] if messages else 'N/A'}"
            )
            soporte_notificado = True

    return JSONResponse({"respuesta": respuesta, "soporte_notificado": soporte_notificado})


# ── Reporte PDF ──────────────────────────────────────────────────────────────────
register_report_pdf_routes(app)


# ── Historial de transacciones ───────────────────────────────────────────────────
register_history_routes(app)


# ── Comparador de acciones ────────────────────────────────────────────────────
register_comparator_routes(app)


# ── Calculadora ISLR ──────────────────────────────────────────────────────────
register_islr_routes(app)


# ── Índice vs Mercado ─────────────────────────────────────────────────────────
register_index_market_routes(app)


# ── Setup Telegram webhook ───────────────────────────────────────────────────────

async def registrar_webhook_telegram():
    """Registra el webhook de Telegram al arrancar la app."""
    import os
    app_url = os.environ.get("APP_URL", "")
    if not app_url:
        return
    webhook_url = f"{app_url}/webhook/telegram"
    from services.telegram import TELEGRAM_API
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(f"{TELEGRAM_API}/setWebhook", json={"url": webhook_url})
            if r.status_code == 200:
                print(f"[Telegram] Webhook registrado: {webhook_url}")
        except Exception as e:
            print(f"[Telegram] Error registrando webhook: {e}")


# ── Inicio ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
