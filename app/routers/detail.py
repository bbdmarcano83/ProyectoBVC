"""Security detail page extracted from legacy main.py without behavior changes."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import get_db
from services.auth import dias_restantes, get_usuario_actual, suscripcion_activa
from services.bvc import (
    _to_float,
    mercado_abierto,
    obtener_datos_bvc,
    obtener_detalle_profundo,
    obtener_historico,
)


async def ver_detalle(request: Request, simbolo: str, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    if not suscripcion_activa(usuario):
        return RedirectResponse(url="/suscripcion", status_code=302)

    simbolo = simbolo.upper()
    datos_bolsa, prof, historico = await asyncio.gather(
        obtener_datos_bvc(), obtener_detalle_profundo(simbolo), obtener_historico(simbolo)
    )
    activo = next((i for i in datos_bolsa if i.get("COD_SIMB") == simbolo), {})

    series_data = []
    volume_data = []
    for m in reversed(historico):
        o = _to_float(m.get("PRECIO_APERT"))
        h = _to_float(m.get("PRECIO_MAX"))
        l = _to_float(m.get("PRECIO_MIN"))
        c = _to_float(m.get("PRECIO_CIE"))
        v = _to_float(m.get("TOT_ACC_NEGOC") or 0)
        monto = _to_float(m.get("TOT_MONTO_NEGOC") or 0)
        ops = _to_float(m.get("TOT_OP_NEGOC") or 0)
        fecha = m.get("FEC", "")
        if any([o, h, l, c]):
            series_data.append({"x": fecha, "y": [o, h, l, c]})
            volume_data.append({"x": fecha, "y": v, "monto": monto, "ops": int(ops), "isUp": c >= o})

    try:
        import pytz

        vet = pytz.timezone("America/Caracas")
        hoy = datetime.now(vet).strftime("%d/%m/%Y")
    except Exception:
        hoy = datetime.now(timezone(timedelta(hours=-4))).strftime("%d/%m/%Y")

    precio_actual = _to_float(activo.get("PRECIO"))
    apert = _to_float(prof.get("HOY_APERT") or precio_actual)
    maximo = _to_float(prof.get("HOY_MAX") or precio_actual)
    minimo = _to_float(prof.get("HOY_MIN") or precio_actual)
    vol_hoy = _to_float(activo.get("VOLUMEN") or 0)

    vela_hoy = None
    if precio_actual > 0:
        vela_hoy = {"x": hoy, "y": [apert, maximo, minimo, precio_actual]}

    vol_hoy_data = None
    if vol_hoy > 0:
        vol_hoy_data = {"x": hoy, "y": vol_hoy, "isUp": precio_actual >= apert}

    return render("detalle.html", {
        "request": request,
        "simbolo": simbolo,
        "activo": activo,
        "prof": prof,
        "series_data": series_data,
        "volume_data": volume_data,
        "vela_hoy": vela_hoy,
        "vol_hoy_data": vol_hoy_data,
        "active": "",
        "usuario": usuario,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(),
    })


def register_detail_routes(app: FastAPI) -> None:
    app.add_api_route("/detalle/{simbolo}", ver_detalle, methods=["GET"], response_class=HTMLResponse)
