"""Authentication routes extracted from legacy main.py without behavior changes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import get_db
from services.auth import autenticar_usuario, crear_token, crear_usuario, get_usuario_actual

router = APIRouter()


@router.get("/landing", response_class=HTMLResponse)
async def landing_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    return render("landing.html", {"request": request, "usuario": usuario})


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if usuario:
        return RedirectResponse(url="/", status_code=302)
    return render("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
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


@router.get("/registro", response_class=HTMLResponse)
async def registro_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if usuario:
        return RedirectResponse(url="/", status_code=302)
    return render("registro.html", {"request": request, "error": None})


@router.post("/registro", response_class=HTMLResponse)
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


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response
