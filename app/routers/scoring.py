"""Scoring handlers extracted from legacy main.py without rule changes."""
from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import ActivoPortafolio, get_db
from services.auth import dias_restantes, get_plan, get_usuario_actual, suscripcion_activa
from services.bvc import mercado_abierto
from services.scoring import calcular_scoring_completo


async def ver_scoring(request: Request, deval: float = 0, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    if not suscripcion_activa(usuario):
        return RedirectResponse(url="/suscripcion", status_code=302)

    plan = get_plan(usuario)
    if plan == "basico":
        return RedirectResponse(url="/suscripcion?mensaje=El scoring requiere plan Intermedio o Pro", status_code=302)

    deval_input = deval if deval > 0 else None
    resultados, deval_usado, metadata = await calcular_scoring_completo(devaluacion_pct=deval_input)

    señales_compra = []
    señales_venta = []

    if plan in ("pro", "trial"):
        señales_compra = [r for r in resultados if r.get("señal_compra")]
        activos_db = db.query(ActivoPortafolio).filter(ActivoPortafolio.usuario_id == usuario.id).all()
        portafolio_map = {a.simbolo: a for a in activos_db}

        for r in resultados:
            simb = r.get("simbolo")
            if simb not in portafolio_map:
                continue
            activo = portafolio_map[simb]
            precio_actual = r.get("precio", 0)
            precio_compra = activo.precio_promedio or 0
            if precio_compra <= 0:
                continue
            ganancia_pct = round(((precio_actual / precio_compra) - 1) * 100, 1)
            motivo = None
            if ganancia_pct >= 50:
                motivo = "ganancia"
            elif r.get("din_score", 0) == 0:
                motivo = "congelado"
            elif r.get("total", 0) < 30:
                motivo = "score_minimo"
            if motivo:
                señales_venta.append({
                    "simbolo": simb,
                    "ganancia_pct": ganancia_pct,
                    "precio_compra": precio_compra,
                    "precio_actual": precio_actual,
                    "cantidad": activo.cantidad,
                    "total": r.get("total", 0),
                    "din_score": r.get("din_score", 0),
                    "motivo": motivo,
                })

    if plan == "intermedio":
        for r in resultados:
            r["caida_pct"] = None
            r["señal_compra"] = False

    return render("scoring.html", {
        "request": request,
        "resultados": resultados,
        "deval": deval_usado,
        "metadata": metadata,
        "ibc_count": sum(1 for r in resultados if r.get("ibc")),
        "alto_count": sum(1 for r in resultados if r.get("accion_label") == "Score alto"),
        "medio_count": sum(1 for r in resultados if r.get("accion_label") == "Score medio"),
        "bajo_count": sum(1 for r in resultados if r.get("accion_label") == "Score bajo"),
        "minimo_count": sum(1 for r in resultados if r.get("accion_label") == "Score mínimo"),
        "señales_compra": señales_compra,
        "señales_venta": señales_venta,
        "plan": plan,
        "active": "scoring",
        "usuario": usuario,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(),
    })


async def api_scoring(deval: float = 0, request: Request = None, db: Session = Depends(get_db)):
    """API JSON para consumo externo o futuras integraciones."""
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    deval_input = deval if deval > 0 else None
    resultados, deval_usado, metadata = await calcular_scoring_completo(devaluacion_pct=deval_input)
    return JSONResponse({"deval": deval_usado, "resultados": resultados, "metadata": metadata})


def register_scoring_routes(app: FastAPI) -> None:
    app.add_api_route("/scoring", ver_scoring, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/api/scoring", api_scoring, methods=["GET"], response_class=JSONResponse)
