"""Profile/account handlers extracted from legacy main.py without behavior changes."""
from __future__ import annotations

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import get_db
from services.auth import (
    dias_restantes,
    get_usuario_actual,
    hash_password,
    verificar_password,
)
from services.bvc import mercado_abierto


async def ver_perfil(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    return render("perfil.html", {
        "request": request,
        "usuario": usuario,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(),
        "active": "",
        "msg_info": None,
        "msg_pass": None,
        "error_pass": False,
    })


async def actualizar_info(
    request: Request,
    nombre: str = Form(...),
    email: str = Form(...),
    broker: str = Form(""),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    usuario.nombre = nombre.strip()
    usuario.email = email.strip().lower()
    db.commit()
    return render("perfil.html", {
        "request": request,
        "usuario": usuario,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(),
        "active": "",
        "msg_info": "Datos actualizados correctamente",
        "msg_pass": None,
        "error_pass": False,
    })


async def cambiar_password(
    request: Request,
    password_actual: str = Form(...),
    password_nueva: str = Form(...),
    password_nueva2: str = Form(...),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)

    if not verificar_password(password_actual, usuario.password_hash):
        return render("perfil.html", {
            "request": request,
            "usuario": usuario,
            "dias": dias_restantes(usuario),
            "mercado": mercado_abierto(),
            "active": "",
            "msg_info": None,
            "msg_pass": "Contraseña actual incorrecta",
            "error_pass": True,
        })
    if password_nueva != password_nueva2:
        return render("perfil.html", {
            "request": request,
            "usuario": usuario,
            "dias": dias_restantes(usuario),
            "mercado": mercado_abierto(),
            "active": "",
            "msg_info": None,
            "msg_pass": "Las contraseñas nuevas no coinciden",
            "error_pass": True,
        })
    if len(password_nueva) < 8:
        return render("perfil.html", {
            "request": request,
            "usuario": usuario,
            "dias": dias_restantes(usuario),
            "mercado": mercado_abierto(),
            "active": "",
            "msg_info": None,
            "msg_pass": "La contraseña debe tener al menos 8 caracteres",
            "error_pass": True,
        })

    usuario.password_hash = hash_password(password_nueva)
    db.commit()
    return render("perfil.html", {
        "request": request,
        "usuario": usuario,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(),
        "active": "",
        "msg_info": None,
        "msg_pass": "Contraseña cambiada correctamente",
        "error_pass": False,
    })


async def eliminar_cuenta(
    request: Request,
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario or not verificar_password(password, usuario.password_hash):
        return RedirectResponse(url="/perfil", status_code=302)
    db.delete(usuario)
    db.commit()
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response


def register_profile_routes(app: FastAPI) -> None:
    app.add_api_route("/perfil", ver_perfil, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/perfil/info", actualizar_info, methods=["POST"])
    app.add_api_route("/perfil/password", cambiar_password, methods=["POST"])
    app.add_api_route("/perfil/eliminar", eliminar_cuenta, methods=["POST"])
