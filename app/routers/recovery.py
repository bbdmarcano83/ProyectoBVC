"""Password recovery handlers extracted from legacy main.py without behavior changes."""
from __future__ import annotations

import asyncio
import os
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import Usuario, get_db
from services.auth import hash_password
from services.email import email_recuperar_password


async def recuperar_page(request: Request):
    return render("recuperar.html", {
        "request": request,
        "modo": "solicitar",
        "error": None,
        "mensaje": None,
        "token": None,
    })


async def recuperar_post(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.email == email.lower().strip()).first()
    if usuario:
        token = secrets.token_urlsafe(32)
        usuario.token_recuperacion = token
        usuario.token_expira = datetime.utcnow() + timedelta(minutes=30)
        db.commit()
        app_url = os.environ.get("APP_URL", "https://caracasbull.com")
        asyncio.create_task(
            asyncio.to_thread(
                email_recuperar_password,
                usuario.email,
                usuario.nombre,
                token,
                app_url,
            )
        )
    return render("recuperar.html", {
        "request": request,
        "modo": "solicitar",
        "error": None,
        "mensaje": "Si el email existe, recibirás un enlace en minutos.",
        "token": None,
    })


async def recuperar_token_page(request: Request, token: str, db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter(Usuario.token_recuperacion == token).first()
    if not usuario or not usuario.token_expira or datetime.utcnow() > usuario.token_expira:
        return render("recuperar.html", {
            "request": request,
            "modo": "expirado",
            "error": None,
            "mensaje": None,
            "token": None,
        })
    return render("recuperar.html", {
        "request": request,
        "modo": "nueva",
        "error": None,
        "mensaje": None,
        "token": token,
    })


async def recuperar_token_post(
    request: Request,
    token: str,
    password: str = Form(...),
    password2: str = Form(...),
    db: Session = Depends(get_db),
):
    usuario = db.query(Usuario).filter(Usuario.token_recuperacion == token).first()
    if not usuario or not usuario.token_expira or datetime.utcnow() > usuario.token_expira:
        return render("recuperar.html", {
            "request": request,
            "modo": "expirado",
            "error": None,
            "mensaje": None,
            "token": None,
        })
    if password != password2:
        return render("recuperar.html", {
            "request": request,
            "modo": "nueva",
            "error": "Las contraseñas no coinciden",
            "mensaje": None,
            "token": token,
        })
    if len(password) < 8:
        return render("recuperar.html", {
            "request": request,
            "modo": "nueva",
            "error": "Mínimo 8 caracteres",
            "mensaje": None,
            "token": token,
        })
    usuario.password_hash = hash_password(password)
    usuario.token_recuperacion = None
    usuario.token_expira = None
    db.commit()
    return render("recuperar.html", {
        "request": request,
        "modo": "ok",
        "error": None,
        "mensaje": None,
        "token": None,
    })


def register_recovery_routes(app: FastAPI) -> None:
    app.add_api_route("/recuperar", recuperar_page, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/recuperar", recuperar_post, methods=["POST"], response_class=HTMLResponse)
    app.add_api_route("/recuperar/{token}", recuperar_token_page, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/recuperar/{token}", recuperar_token_post, methods=["POST"], response_class=HTMLResponse)
