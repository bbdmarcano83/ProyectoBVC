"""Stock comparator route extracted from legacy main.py without behavior changes."""
from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import get_db
from services.auth import dias_restantes, get_usuario_actual
from services.bvc import _to_float, mercado_abierto, obtener_datos_bvc


async def comparador(request: Request, s1: str = "", s2: str = "", s3: str = "", db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    datos_bolsa = await obtener_datos_bvc()
    simbolos = sorted([i["COD_SIMB"] for i in datos_bolsa])
    mapa = {i["COD_SIMB"]: i for i in datos_bolsa}
    datos_comparacion = []
    for s in [s1, s2, s3]:
        if s and s in mapa:
            item = mapa[s]
            datos_comparacion.append({
                "simbolo": s,
                "precio": _to_float(item.get("PRECIO")),
                "var_rel": _to_float(item.get("VAR_REL")),
                "vol_transado": _to_float(item.get("MONTO_EFECTIVO")),
                "titulos": item.get("VOLUMEN", "—"),
                "p_compra": _to_float(item.get("PRE_CMP_1")),
                "p_venta": _to_float(item.get("PRE_VTA_1")),
            })
    return render("comparador.html", {
        "request": request, "usuario": usuario, "simbolos": simbolos,
        "seleccionados": [s1, s2, s3],
        "datos_comparacion": datos_comparacion if datos_comparacion else None,
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(), "active": "",
    })


def register_comparator_routes(app: FastAPI) -> None:
    app.add_api_route("/comparador", comparador, methods=["GET"], response_class=HTMLResponse)
