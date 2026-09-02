import sys
sys.setrecursionlimit(5000)
import uvicorn
import asyncio
import os
import json
import httpx

from fastapi import FastAPI, Form, Request, Depends, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from database import init_db, get_db, SessionLocal, AlertaPrecio, TransaccionHistorial
from services.alertas_worker import loop_alertas
from services.bvc import obtener_datos_bvc, obtener_detalle_profundo, obtener_historico, _to_float, formatear_bs, formatear_entero, formatear_millones, mercado_abierto, obtener_tasa_bcv
from services.portafolio import calcular_fila, resumen_portafolio
from services.auth import (
    crear_usuario, autenticar_usuario, crear_token,
    get_usuario_actual, require_usuario, require_suscripcion,
    suscripcion_activa, dias_restantes, hash_password, get_plan
)
from services.pagos import crear_pago, verificar_firma_ipn, procesar_webhook, verificar_estado_pago
from services.importador import importar_archivo
import httpx as httpx_client
from services.pdf_reporte import generar_reporte
from services.pdf_reporte import generar_reporte
from services.email import email_recuperar_password, email_bienvenida
from app.startup import run_startup
from app.factory import create_app
from app.templating import render
from app.routers.auth import register_auth_routes
from app.routers.subscription import register_subscription_routes
from app.routers.market import register_market_routes
from app.routers.bitacora import register_bitacora_routes
from app.routers.alerts import register_alert_routes
from app.routers.scoring import register_scoring_routes
from app.routers.profile import register_profile_routes
from app.routers.detail import register_detail_routes
from app.routers.api_misc import register_misc_api_routes
from app.routers.recovery import register_recovery_routes
from app.routers.portfolio import register_portfolio_routes
from app.routers.watchlist import register_watchlist_routes
from app.routers.admin import register_admin_routes
from app.routers.pwa import register_pwa_routes
from app.routers.portfolio_import import register_portfolio_import_routes
from app.routers.portfolio_pdf import register_portfolio_pdf_routes
from app.routers.report_pdf import register_report_pdf_routes
from app.routers.chat import register_primary_chat_routes, register_secondary_chat_routes
from app.routers.history import register_history_routes
from app.routers.comparator import register_comparator_routes
from app.routers.islr import register_islr_routes
from app.routers.index_market import register_index_market_routes
from app.routers.legacy_notifications import register_legacy_notification_routes, registrar_webhook_telegram
from database import ActivoPortafolio, Watchlist

app = create_app()

# ── Init DB al arrancar ────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    # `registrar_webhook_telegram` se resuelve al ejecutar startup, después de
    # que el módulo completo haya terminado de importarse.
    await run_startup(registrar_webhook_telegram)

# ── Auth / Suscripción ─────────────────────────────────────────────────────────
register_auth_routes(app)
register_subscription_routes(app)


# ── Inicio / Pizarra ───────────────────────────────────────────────────────────
register_market_routes(app)


# ── Scoring (Rotación Sectorial) ──────────────────────────────────────────────
register_scoring_routes(app)


# ── Alertas de cierre Telegram ────────────────────────────────────────────────
register_alert_routes(app)


# ── Bitácora ──────────────────────────────────────────────────────────────────
register_bitacora_routes(app)


# ── Portafolio ────────────────────────────────────────────────────────────────
register_portfolio_routes(app)


# ── Detalle ───────────────────────────────────────────────────────────────────
register_detail_routes(app)


# ── Perfil ───────────────────────────────────────────────────────────────────────
register_profile_routes(app)


# ── Telegram / Alertas legacy ───────────────────────────────────────────────────
register_legacy_notification_routes(app)


# ── API endpoints ────────────────────────────────────────────────────────────────
register_misc_api_routes(app)


# ── Recuperar contraseña ─────────────────────────────────────────────────────────
register_recovery_routes(app)


# ── Chat Asistente ───────────────────────────────────────────────────────────────
register_primary_chat_routes(app)


# ── Reporte PDF ──────────────────────────────────────────────────────────────────
register_portfolio_pdf_routes(app)


# ── Watchlist ────────────────────────────────────────────────────────────────────
register_watchlist_routes(app)


# ── Importar portafolio ───────────────────────────────────────────────────────
register_portfolio_import_routes(app)


# ── Admin ─────────────────────────────────────────────────────────────────────
register_admin_routes(app)


# ── PWA ───────────────────────────────────────────────────────────────────────
register_pwa_routes(app)


# ── Chat Asistente ───────────────────────────────────────────────────────────────
register_secondary_chat_routes(app)


# ── Reporte PDF ──────────────────────────────────────────────────────────────────
register_report_pdf_routes(app)


# ── Historial de transacciones ───────────────────────────────────────────────────
register_history_routes(app)


# ── Comparador de acciones ────────────────────────────────────────────────────
register_comparator_routes(app)


# ── Calculadora ISLR ──────────────────────────────────────────────────────────
register_islr_routes(app)


# ── Índice vs Mercado ─────────────────────────────────────────────────────────
register_index_market_routes(app)


# ── Inicio ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
