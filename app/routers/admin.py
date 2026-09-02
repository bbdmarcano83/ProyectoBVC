"""Admin handlers extracted from legacy main.py without behavior changes."""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import Suscripcion, Usuario, get_db
from services.auth import dias_restantes, get_usuario_actual
from services.bvc import mercado_abierto


async def admin_panel(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario or not usuario.es_admin:
        return RedirectResponse(url="/", status_code=302)
    usuarios = db.query(Usuario).order_by(Usuario.creado_en.desc()).all()
    total = len(usuarios)
    activas = sum(1 for u in usuarios if u.suscripcion and u.suscripcion.activa)
    plan_pro = sum(1 for u in usuarios if u.suscripcion and u.suscripcion.plan == "pro")
    plan_bas = sum(1 for u in usuarios if u.suscripcion and u.suscripcion.plan == "basico")
    trial = sum(1 for u in usuarios if u.suscripcion and u.suscripcion.plan == "trial")
    con_tg = sum(1 for u in usuarios if u.telegram_chat_id)
    return render("admin.html", {
        "request": request,
        "usuario": usuario,
        "usuarios": usuarios,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(),
        "active": "",
        "stats": {
            "total_usuarios": total,
            "activas": activas,
            "plan_pro": plan_pro,
            "plan_basico": plan_bas,
            "trial": trial,
            "con_telegram": con_tg,
        },
    })


async def admin_activar(
    request: Request,
    usuario_id: int = Form(...),
    plan: str = Form("pro"),
    db: Session = Depends(get_db),
):
    admin = get_usuario_actual(request, db)
    if not admin or not admin.es_admin:
        return RedirectResponse(url="/", status_code=302)
    sus = db.query(Suscripcion).filter(Suscripcion.usuario_id == usuario_id).first()
    if sus:
        sus.plan = plan
        sus.activa = True
        sus.fecha_vence = datetime.utcnow() + timedelta(days=30)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)


async def admin_desactivar(request: Request, usuario_id: int = Form(...), db: Session = Depends(get_db)):
    admin = get_usuario_actual(request, db)
    if not admin or not admin.es_admin:
        return RedirectResponse(url="/", status_code=302)
    sus = db.query(Suscripcion).filter(Suscripcion.usuario_id == usuario_id).first()
    if sus:
        sus.activa = False
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


def register_admin_routes(app: FastAPI) -> None:
    app.add_api_route("/admin", admin_panel, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/admin/activar", admin_activar, methods=["POST"])
    app.add_api_route("/admin/desactivar", admin_desactivar, methods=["POST"])
