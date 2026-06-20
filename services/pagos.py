import os
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from database import Suscripcion, PagoHistorial, Usuario

NOWPAYMENTS_API_KEY = os.environ.get("NOWPAYMENTS_API_KEY", "")
NOWPAYMENTS_IPN_SECRET = os.environ.get("NOWPAYMENTS_IPN_SECRET", "")
NOWPAYMENTS_URL = "https://api.nowpayments.io/v1"

# Precios por plan
PRECIOS = {
    "basico": 1.5,
    "pro": 2.99,  # Precio especial de lanzamiento
}

DURACION_DIAS = {
    "basico": 30,
    "pro": 30,
}


async def crear_pago(usuario_id: int, plan: str, email: str) -> Optional[dict]:
    """Crea una orden de pago en NOWPayments y devuelve los datos."""
    key = os.environ.get("NOWPAYMENTS_API_KEY", "")
    print(f"[NOWPayments] API Key presente: {bool(key)}, longitud: {len(key)}")
    if not key:
        print("[NOWPayments] ERROR: API Key no configurada")
        return None

    monto = PRECIOS.get(plan, 1.5)

    payload = {
        "price_amount": monto,
        "price_currency": "usd",
        "pay_currency": "usdtbsc",
        "order_id": f"cb_{usuario_id}_{plan}_{int(datetime.utcnow().timestamp())}",
        "order_description": f"Caracas Bull — Plan {plan.capitalize()} (30 días)",
        "ipn_callback_url": os.environ.get("APP_URL", "") + "/webhook/nowpayments",
        "success_url": os.environ.get("APP_URL", "") + "/suscripcion/exitosa",
        "cancel_url": os.environ.get("APP_URL", "") + "/suscripcion",
    }

    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{NOWPAYMENTS_URL}/payment",
                json=payload,
                headers={
                    "x-api-key": key,
                    "Content-Type": "application/json",
                },
                timeout=10.0,
            )
            print(f"[NOWPayments] Status: {r.status_code}, Response: {r.text[:300]}")
            if r.status_code == 201:
                return r.json()
            else:
                print(f"[NOWPayments] Error {r.status_code}: {r.text}")
        except Exception as e:
            print(f"[NOWPayments] Error creando pago: {e}")
    return None


def verificar_firma_ipn(body_bytes: bytes, firma_recibida: str) -> bool:
    """Verifica que el webhook viene realmente de NOWPayments."""
    if not NOWPAYMENTS_IPN_SECRET:
        return True  # en desarrollo sin secret, aceptar todo
    firma_esperada = hmac.new(
        NOWPAYMENTS_IPN_SECRET.encode(),
        body_bytes,
        hashlib.sha512,
    ).hexdigest()
    return hmac.compare_digest(firma_esperada, firma_recibida)


def procesar_webhook(db: Session, datos: dict) -> bool:
    """Procesa la notificación de NOWPayments y activa la suscripción si el pago es válido."""
    payment_status = datos.get("payment_status")
    payment_id     = str(datos.get("payment_id", ""))
    order_id       = datos.get("order_id", "")

    # Extraer usuario_id y plan del order_id: "cb_{usuario_id}_{plan}_{timestamp}"
    try:
        partes     = order_id.split("_")
        usuario_id = int(partes[1])
        plan       = partes[2]
    except (IndexError, ValueError):
        print(f"[NOWPayments] order_id inválido: {order_id}")
        return False

    # Guardar en historial
    historial = PagoHistorial(
        usuario_id=usuario_id,
        nowpayments_id=payment_id,
        plan=plan,
        monto=PRECIOS.get(plan, 1.5),
        status=payment_status,
    )
    db.add(historial)

    # Solo activar si el pago está confirmado
    if payment_status in ("finished", "confirmed"):
        suscripcion = db.query(Suscripcion).filter(
            Suscripcion.usuario_id == usuario_id
        ).first()

        if suscripcion:
            ahora = datetime.utcnow()
            # Si ya tiene días restantes, extender desde esa fecha
            if suscripcion.fecha_vence and suscripcion.fecha_vence > ahora:
                nueva_fecha = suscripcion.fecha_vence + timedelta(days=DURACION_DIAS[plan])
            else:
                nueva_fecha = ahora + timedelta(days=DURACION_DIAS[plan])

            suscripcion.plan         = plan
            suscripcion.activa       = True
            suscripcion.fecha_vence  = nueva_fecha
            suscripcion.pago_id      = payment_id
            suscripcion.pago_status  = payment_status
            suscripcion.monto_usd    = PRECIOS.get(plan, 1.5)

        db.commit()
        print(f"[NOWPayments] Suscripción activada — usuario {usuario_id}, plan {plan}")
        return True

    db.commit()
    return False


async def verificar_estado_pago(payment_id: str) -> Optional[dict]:
    """Consulta el estado actual de un pago en NOWPayments."""
    if not NOWPAYMENTS_API_KEY:
        return None
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{NOWPAYMENTS_URL}/payment/{payment_id}",
                headers={"x-api-key": NOWPAYMENTS_API_KEY},
                timeout=10.0,
            )
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"[NOWPayments] Error verificando pago: {e}")
    return None
