"""Portfolio-versus-market index route extracted from legacy main.py without behavior changes."""
from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.templating import render
from database import ActivoPortafolio, get_db
from services.auth import dias_restantes, get_usuario_actual
from services.bvc import _to_float, mercado_abierto, obtener_datos_bvc, obtener_tasa_bcv
from services.portafolio import calcular_fila


async def indice_mercado(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    datos_bolsa = await obtener_datos_bvc()
    tasa_auto = await obtener_tasa_bcv()
    config_tasa = tasa_auto if tasa_auto > 0 else 0
    activos_db = db.query(ActivoPortafolio).filter(ActivoPortafolio.usuario_id == usuario.id).all()
    portafolio = {a.simbolo: {"cantidad": a.cantidad, "precio_promedio": a.precio_promedio,
                               "comision": a.comision, "registro": a.registro, "iva": a.iva}
                  for a in activos_db}
    mapa_precios = {i["COD_SIMB"]: _to_float(i.get("PRECIO")) for i in datos_bolsa}
    vars_hoy = {i["COD_SIMB"]: _to_float(i.get("VAR_REL")) for i in datos_bolsa}
    total_mkt = sum(
        _to_float(d["cantidad"]) * mapa_precios.get(s, _to_float(d["precio_promedio"]))
        for s, d in portafolio.items()
    )
    filas = [
        calcular_fila(s, d, mapa_precios.get(s, _to_float(d["precio_promedio"])), total_mkt, config_tasa)
        for s, d in portafolio.items()
    ]
    rend_port = sum(f["rend_pct"] * f["peso_pct"] / 100 for f in filas) if filas else 0
    todas_vars = [_to_float(i.get("VAR_REL")) for i in datos_bolsa]
    rend_mercado = sum(todas_vars) / len(todas_vars) if todas_vars else 0

    return render("indice.html", {
        "request": request, "usuario": usuario, "filas": filas,
        "rend_port": rend_port, "rend_mercado": rend_mercado,
        "vars_hoy": vars_hoy,
        "vars_hoy_list": [vars_hoy.get(f["simb"], 0) for f in filas],
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(), "active": "",
    })


def register_index_market_routes(app: FastAPI) -> None:
    app.add_api_route("/indice", indice_mercado, methods=["GET"], response_class=HTMLResponse)
