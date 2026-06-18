import httpx
import asyncio
import time
from typing import Optional

# ─── Caché simple en memoria (60 segundos) ───────────────────────────────────
_cache: dict = {}
CACHE_TTL = 60  # segundos

BVC_URL = "https://www.bolsadecaracas.com/wp-admin/admin-ajax.php"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/x-www-form-urlencoded",
}


def _cache_get(key: str) -> Optional[any]:
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(key: str, data: any) -> None:
    _cache[key] = {"data": data, "ts": time.time()}


async def obtener_datos_bvc() -> list[dict]:
    """Trae resumen + detalle del mercado de renta variable, con caché de 60s."""
    cached = _cache_get("pizarra")
    if cached:
        return cached

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r1, r2 = await asyncio.gather(
                client.post(BVC_URL, data={"action": "resumenMercadoRentaVariable"}, headers=HEADERS),
                client.post(BVC_URL, data={"action": "get_cotizaciones"}, headers=HEADERS),
            )
            datos_resumen: list = r1.json()
            datos_detalle: list = r2.json().get("response", [])
        except Exception as e:
            print(f"[BVC] Error al obtener datos: {e}")
            return _cache.get("pizarra", {}).get("data", [])  # devuelve caché viejo si existe

    mapa_detalle = {item["COD_SIMB"]: item for item in datos_detalle}
    for item in datos_resumen:
        simb = item.get("COD_SIMB")
        if simb in mapa_detalle:
            item.update(mapa_detalle[simb])

    # Ordenar por variación descendente
    datos_resumen.sort(key=lambda x: _to_float(x.get("VAR_REL", 0)), reverse=True)

    _cache_set("pizarra", datos_resumen)
    return datos_resumen


async def obtener_detalle_profundo(simbolo: str) -> dict:
    """Profundidad de mercado (6 niveles), ISIN, acciones circulantes, capitalización."""
    key = f"detalle_{simbolo}"
    cached = _cache_get(key)
    if cached:
        return cached

    payload = {"action": "getSimbolosDetalle", "simbolo": simbolo, "tipo": "rv"}
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            r = await client.post(BVC_URL, data=payload, headers=HEADERS)
            full_json = r.json()
            data = full_json.get("response", {})
            encab = data.get("cur_encab_simb_rv", [{}])[0]
            cap   = data.get("cur_cap_simb_rv", [{}])[0]
            prof  = data.get("cur_con_lib_ord_rv", [{}])[0]

            resultado = {
                **prof,
                "ISIN":           encab.get("COD_ISIN", "N/A"),
                "ACC_CIRC":       encab.get("ACC_CIRC", "N/A"),
                "CAPITALIZACION": cap.get("CAPITALI_BS", "N/A"),
            }
            _cache_set(key, resultado)
            return resultado
        except Exception as e:
            print(f"[BVC] Error detalle {simbolo}: {e}")
            return {}


async def obtener_historico(simbolo: str) -> list[dict]:
    """Histórico de precios OHLC del símbolo."""
    key = f"hist_{simbolo}"
    cached = _cache_get(key)
    if cached:
        return cached

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            r = await client.post(BVC_URL, data={"action": "getHistoricoSimbolo", "simbolo": simbolo}, headers=HEADERS)
            datos = r.json().get("cur_hist_mov_emisora", [])
            _cache_set(key, datos)
            return datos
        except Exception as e:
            print(f"[BVC] Error histórico {simbolo}: {e}")
            return []


# ─── Utilidades numéricas ─────────────────────────────────────────────────────

def _to_float(valor, default: float = 0.0) -> float:
    """Convierte cualquier formato numérico venezolano o estándar a float."""
    if valor is None or valor == "":
        return default
    try:
        s = str(valor).strip()
        # Formato "1.234,56" → "1234.56"
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        return float(s)
    except (ValueError, TypeError):
        return default


def formatear_bs(valor) -> str:
    """Formatea un número como moneda venezolana: 1.234.567,89"""
    try:
        num = _to_float(valor)
        return f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(valor)
