"""Small JSON API handlers extracted from legacy main.py."""
from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db
from services.auth import get_usuario_actual
from services.bvc import _to_float, obtener_datos_bvc, obtener_tasa_bcv


async def api_tasa():
    """Devuelve la tasa BCV actual."""
    tasa = await obtener_tasa_bcv()
    return JSONResponse({"tasa": tasa, "fuente": "BCV" if tasa > 0 else "manual"})


async def api_precio(simbolo: str, request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    datos = await obtener_datos_bvc()
    activo = next((i for i in datos if i.get("COD_SIMB") == simbolo.upper()), None)
    if not activo:
        return JSONResponse({"error": "no encontrado"}, status_code=404)
    return JSONResponse({
        "precio": _to_float(activo.get("PRECIO")),
        "var_rel": _to_float(activo.get("VAR_REL")),
        "var_abs": _to_float(activo.get("VAR_ABS")),
    })


def register_misc_api_routes(app: FastAPI) -> None:
    app.add_api_route("/api/tasa", api_tasa, methods=["GET"])
    app.add_api_route("/api/precio/{simbolo}", api_precio, methods=["GET"])
