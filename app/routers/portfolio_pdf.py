"""Portfolio PDF handler extracted from legacy main.py without behavior changes."""
from __future__ import annotations

import io
from datetime import datetime

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from database import ActivoPortafolio, get_db
from services.auth import get_usuario_actual
from services.bvc import _to_float, obtener_datos_bvc, obtener_tasa_bcv
from services.pdf_reporte import generar_reporte
from services.portafolio import calcular_fila, resumen_portafolio


async def descargar_pdf(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)

    datos_bolsa = await obtener_datos_bvc()
    tasa_auto = await obtener_tasa_bcv()
    config_tasa = tasa_auto if tasa_auto > 0 else 0

    activos_db = db.query(ActivoPortafolio).filter(ActivoPortafolio.usuario_id == usuario.id).all()
    portafolio = {
        a.simbolo: {
            "cantidad": a.cantidad,
            "precio_promedio": a.precio_promedio,
            "comision": a.comision,
            "registro": a.registro,
            "iva": a.iva,
        }
        for a in activos_db
    }
    mapa_precios = {i["COD_SIMB"]: _to_float(i.get("PRECIO") or 0) for i in datos_bolsa}
    total_mkt = sum(
        _to_float(d["cantidad"]) * mapa_precios.get(s, _to_float(d["precio_promedio"]))
        for s, d in portafolio.items()
    )
    filas = [
        calcular_fila(s, d, mapa_precios.get(s, _to_float(d["precio_promedio"])), total_mkt, config_tasa)
        for s, d in portafolio.items()
    ]
    resumen = resumen_portafolio(portafolio, datos_bolsa, config_tasa)

    pdf_bytes = generar_reporte(usuario, filas, resumen, config_tasa)
    nombre = f"CaracasBull_Reporte_{datetime.now().strftime('%Y%m')}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nombre}"},
    )


def register_portfolio_pdf_routes(app: FastAPI) -> None:
    app.add_api_route("/portafolio/pdf", descargar_pdf, methods=["GET"])
