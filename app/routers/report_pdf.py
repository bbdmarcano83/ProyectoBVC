"""Legacy /reporte/pdf handler extracted from main.py without behavior changes."""
from __future__ import annotations

from datetime import datetime

from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from database import ActivoPortafolio, get_db
from services.auth import get_usuario_actual
from services.bvc import _to_float, obtener_datos_bvc, obtener_tasa_bcv
from services.pdf_reporte import generar_reporte
from services.portafolio import calcular_fila, resumen_portafolio


async def descargar_reporte(request: Request, db: Session = Depends(get_db)):
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

    mapa_precios = {i["COD_SIMB"]: _to_float(i.get("PRECIO")) for i in datos_bolsa}
    total_mkt = sum(
        _to_float(d["cantidad"]) * mapa_precios.get(s, _to_float(d["precio_promedio"]))
        for s, d in portafolio.items()
    )

    filas = [
        calcular_fila(s, d, mapa_precios.get(s, _to_float(d["precio_promedio"])), total_mkt, config_tasa)
        for s, d in portafolio.items()
    ]
    resumen = resumen_portafolio(portafolio, datos_bolsa, config_tasa)

    plan = usuario.suscripcion.plan if usuario.suscripcion else "trial"
    mes = datetime.now().strftime("%B %Y")

    pdf_bytes = generar_reporte(
        usuario_nombre=usuario.nombre,
        usuario_email=usuario.email,
        plan=plan,
        filas=filas,
        resumen=resumen,
        tasa=config_tasa,
        mes=mes,
    )

    filename = f"reporte_caracasbull_{datetime.now().strftime('%Y%m')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def register_report_pdf_routes(app: FastAPI) -> None:
    app.add_api_route("/reporte/pdf", descargar_reporte, methods=["GET"])
