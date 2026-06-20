import httpx
import asyncio
import os

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8828374649:AAFSk1n57WKwxjtCG3500wPErr2B84Cces4")
TELEGRAM_API   = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


async def enviar_mensaje(chat_id: str, texto: str) -> bool:
    """Envía un mensaje a un chat de Telegram."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.post(f"{TELEGRAM_API}/sendMessage", json={
                "chat_id": chat_id,
                "text": texto,
                "parse_mode": "HTML",
            })
            return r.status_code == 200
        except Exception as e:
            print(f"[Telegram] Error enviando mensaje: {e}")
            return False


async def obtener_updates(offset: int = 0) -> list:
    """Obtiene mensajes nuevos del bot."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(f"{TELEGRAM_API}/getUpdates", params={
                "offset": offset,
                "timeout": 1,
            })
            if r.status_code == 200:
                return r.json().get("result", [])
        except Exception as e:
            print(f"[Telegram] Error obteniendo updates: {e}")
        return []


async def verificar_codigo(chat_id: str, codigo: str, db) -> bool:
    """Verifica el código de vinculación y vincula el chat_id al usuario."""
    from database import Usuario
    usuario = db.query(Usuario).filter(Usuario.telegram_codigo == codigo).first()
    if not usuario:
        await enviar_mensaje(chat_id, "❌ Código inválido o expirado. Genera uno nuevo en tu perfil.")
        return False

    usuario.telegram_chat_id = chat_id
    usuario.telegram_codigo   = None
    db.commit()

    await enviar_mensaje(chat_id, f"""✅ <b>¡Cuenta vinculada!</b>

Hola <b>{usuario.nombre}</b>, tu cuenta de Caracas Bull está conectada.

Recibirás alertas aquí cuando tus acciones suban o bajen el % que configures.

<i>CaracasBull 🐂 — Bolsa de Caracas en tiempo real</i>""")
    return True


async def enviar_alerta_precio(chat_id: str, simbolo: str, precio: float,
                                variacion: float, tipo: str) -> bool:
    """Envía una alerta de precio al usuario."""
    emoji  = "🟢" if tipo == "subida" else "🔴"
    signo  = "+" if variacion > 0 else ""
    precio_fmt = f"{precio:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    texto = f"""{emoji} <b>Alerta de precio — {simbolo}</b>

💰 Precio actual: <b>{precio_fmt} Bs</b>
📊 Variación: <b>{signo}{variacion:.2f}%</b>

<a href="https://proyectobvc.onrender.com/detalle/{simbolo}">Ver en Caracas Bull →</a>

<i>CaracasBull 🐂</i>"""

    return await enviar_mensaje(chat_id, texto)
