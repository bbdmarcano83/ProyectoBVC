import os
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from database import Suscripcion, PagoHistorial

NOWPAYMENTS_URL = "https://api.nowpayments.io/v1"
PRECIOS = {"basico": 1.5, "pro": 2.99}
DURACION_DIAS = {"basico": 30, "pro": 30}
VALID_FINAL_STATUSES = {"finished", "confirmed"}


def _api_key() -> str:
    return os.environ.get("NOWPAYMENTS_API_KEY", "").strip()


def _ipn_secret() -> str:
    return os.environ.get("NOWPAYMENTS_IPN_SECRET", "").strip()


async def crear_pago(usuario_id: int, plan: str, email: str) -> Optional[dict]:
    key = _api_key()
    app_url = os.environ.get("APP_URL", "").strip().rstrip("/")
    if not key or not app_url or plan not in PRECIOS:
        print("[NOWPayments] Configuración incompleta o plan inválido")
        return None

    payload = {
        "price_amount": PRECIOS[plan],
        "price_currency": "usd",
        "pay_currency": "usdtbsc",
        "order_id": f"cb_{usuario_id}_{plan}_{int(datetime.utcnow().timestamp())}",
        "order_description": f"Caracas Bull — Plan {plan.capitalize()} (30 días)",
        "ipn_callback_url": app_url + "/webhook/nowpayments",
        "success_url": app_url + "/suscripcion/exitosa",
        "cancel_url": app_url + "/suscripcion",
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.post(
                f"{NOWPAYMENTS_URL}/payment",
                json=payload,
                headers={"x-api-key": key, "Content-Type": "application/json"},
            )
        if r.status_code == 201:
            return r.json()
        print(f"[NOWPayments] Error creando pago status={r.status_code}")
    except Exception as exc:
        print(f"[NOWPayments] Error creando pago: {type(exc).__name__}")
    return None


def verificar_firma_ipn(body_bytes: bytes, firma_recibida: str) -> bool:
    """Fail-closed: sin secreto configurado ninguna IPN es válida."""
    secret = _ipn_secret()
    if len(secret) < 24 or not firma_recibida:
        return False
    firma_esperada = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha512).hexdigest()
    return hmac.compare_digest(firma_esperada, firma_recibida.strip())


def _parse_order_id(order_id: str) -> tuple[int, str] | None:
    try:
        partes = order_id.split("_")
        if len(partes) != 4 or partes[0] != "cb":
            return None
        usuario_id = int(partes[1])
        plan = partes[2]
        if usuario_id <= 0 or plan not in PRECIOS:
            return None
        return usuario_id, plan
    except (TypeError, ValueError):
        return None


def procesar_webhook(db: Session, datos: dict) -> bool:
    payment_status = str(datos.get("payment_status", "")).lower().strip()
    payment_id = str(datos.get("payment_id", "")).strip()
    order_id = str(datos.get("order_id", "")).strip()
    parsed = _parse_order_id(order_id)
    if not payment_id or not parsed:
        return False
    usuario_id, plan = parsed

    # Idempotencia: NOWPayments puede reintentar la misma notificación.
    existente = db.query(PagoHistorial).filter(
        PagoHistorial.nowpayments_id == payment_id,
        PagoHistorial.status == payment_status,
    ).first()
    if existente:
        return payment_status in VALID_FINAL_STATUSES

    historial = PagoHistorial(
        usuario_id=usuario_id,
        nowpayments_id=payment_id,
        plan=plan,
        monto=PRECIOS[plan],
        status=payment_status,
    )
    db.add(historial)

    if payment_status not in VALID_FINAL_STATUSES:
        db.commit()
        return False

    suscripcion = db.query(Suscripcion).filter(Suscripcion.usuario_id == usuario_id).first()
    if not suscripcion:
        db.rollback()
        return False

    ahora = datetime.utcnow()
    base = suscripcion.fecha_vence if suscripcion.fecha_vence and suscripcion.fecha_vence > ahora else ahora
    suscripcion.plan = plan
    suscripcion.activa = True
    suscripcion.fecha_vence = base + timedelta(days=DURACION_DIAS[plan])
    suscripcion.pago_id = payment_id
    suscripcion.pago_status = payment_status
    suscripcion.monto_usd = PRECIOS[plan]
    db.commit()
    print(f"[NOWPayments] Pago confirmado payment_id={payment_id} usuario={usuario_id} plan={plan}")
    return True


async def verificar_estado_pago(payment_id: str) -> Optional[dict]:
    key = _api_key()
    if not key or not payment_id:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{NOWPAYMENTS_URL}/payment/{payment_id}", headers={"x-api-key": key})
        if r.status_code == 200:
            return r.json()
    except Exception as exc:
        print(f"[NOWPayments] Error verificando pago: {type(exc).__name__}")
    return None
