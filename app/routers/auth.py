"""Authentication route handlers extracted from legacy main.py.

Registration uses FastAPI.add_api_route directly because this project installs
FastAPI bootstraps during service import and APIRouter.include_router has shown
empty-route behavior under reload/contract tests.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import get_db
from services.auth import autenticar_usuario, crear_token, crear_usuario, get_usuario_actual


async def landing_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    return render("landing.html", {"request": request, "usuario": usuario})


async def login_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if usuario:
        return RedirectResponse(url="/", status_code=302)
    return render("login.html", {"request": request, "error": None})


async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    usuario = autenticar_usuario(db, email, password)
    if not usuario:
        return render("login.html", {"request": request, "error": "Email o contraseña incorrectos"})
    token = crear_token({"sub": str(usuario.id)})
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("access_token", token, httponly=True, max_age=60*60*24*7, samesite="lax")
    return response


async def registro_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if usuario:
        return RedirectResponse(url="/", status_code=302)
    return render("registro.html", {"request": request, "error": None})


async def registro_post(
    request: Request,
    nombre: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
    db: Session = Depends(get_db),
):
    if password != password2:
        return render("registro.html", {"request": request, "error": "Las contraseñas no coinciden"})
    if len(password) < 8:
        return render("registro.html", {"request": request, "error": "La contraseña debe tener al menos 8 caracteres"})
    try:
        usuario = crear_usuario(db, nombre, email, password)
    except ValueError as exc:
        return render("registro.html", {"request": request, "error": str(exc)})
    token = crear_token({"sub": str(usuario.id)})
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("access_token", token, httponly=True, max_age=60*60*24*7, samesite="lax")
    return response


async def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response


def register_auth_routes(app: FastAPI) -> None:
    app.add_api_route("/landing", landing_page, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/login", login_page, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/login", login_post, methods=["POST"], response_class=HTMLResponse)
    app.add_api_route("/registro", registro_page, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/registro", registro_post, methods=["POST"], response_class=HTMLResponse)
    app.add_api_route("/logout", logout, methods=["GET"])
