"""Alert dispatch endpoint extracted from legacy main.py without behavior changes."""
from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import get_db


async def disparar_alertas_cierre(request: Request, key: str = "", db: Session = Depends(get_db)):
    """
    Endpoint para disparar alertas de cierre.
    Protegido por clave secreta para que solo el cron lo llame.
    Configurar cron job en Render a las 17:15 UTC (1:15 PM VET).
    """
    clave = os.environ.get("ALERTA_SECRET", "caracasbull-alerta-2026")
    if key != clave:
        return JSONResponse({"error": "No autorizado"}, status_code=401)

    from services.alertas_cierre import enviar_alertas_cierre

    resultado = await enviar_alertas_cierre()
    return JSONResponse(resultado)


def register_alert_routes(app: FastAPI) -> None:
    app.add_api_route(
        "/api/alertas-cierre",
        disparar_alertas_cierre,
        methods=["GET"],
        response_class=JSONResponse,
    )
