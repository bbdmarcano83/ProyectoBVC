"""Legacy chat routes extracted from main.py, preserving duplicate registrations."""
from __future__ import annotations

import os

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import get_db
from services.auth import dias_restantes, get_usuario_actual
from services.bvc import mercado_abierto
from services.telegram import enviar_mensaje


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


async def _chat_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    return render("chat.html", {
        "request": request, "usuario": usuario,
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(), "active": "",
    })


async def _chat_api(request: Request, db: Session = Depends(get_db)):
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
            gemini_messages = []
            for m in messages[-10:]:
                role = "user" if m["role"] == "user" else "model"
                gemini_messages.append({"role": role, "parts": [{"text": m["content"]}]})

            async with httpx.AsyncClient(timeout=30.0) as client:
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

    soporte_notificado = False
    if necesita_soporte and usuario.telegram_chat_id:
        admin_chat = os.environ.get("ADMIN_TELEGRAM_CHAT_ID", "")
        if admin_chat:
            await enviar_mensaje(
                admin_chat,
                f"🆘 <b>Soporte requerido</b>\n"
                f"Usuario: <b>{usuario.nombre}</b> ({usuario.email})\n"
                f"Mensaje: {messages[-1]['content'] if messages else 'N/A'}"
            )
            soporte_notificado = True

    return JSONResponse({"respuesta": respuesta, "soporte_notificado": soporte_notificado})


def _register_chat_pair(app: FastAPI) -> None:
    app.add_api_route("/chat", _chat_page, methods=["GET"], response_class=HTMLResponse, name="chat_page")
    app.add_api_route("/chat", _chat_api, methods=["POST"], name="chat_api")


def register_primary_chat_routes(app: FastAPI) -> None:
    _register_chat_pair(app)


def register_secondary_chat_routes(app: FastAPI) -> None:
    _register_chat_pair(app)
