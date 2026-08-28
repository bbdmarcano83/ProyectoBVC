import json
import os
from typing import Optional
from services.bvc import _to_float

PORTAFOLIO_FILE = "portafolio.json"
CONFIG_FILE = "config.json"


# ─── Persistencia ─────────────────────────────────────────────────────────────

def cargar_portafolio() -> dict:
    if not os.path.exists(PORTAFOLIO_FILE):
        _guardar_json(PORTAFOLIO_FILE, {})
    return _cargar_json(PORTAFOLIO_FILE)


def guardar_portafolio(data: dict) -> None:
    _guardar_json(PORTAFOLIO_FILE, data)


def cargar_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        _guardar_json(CONFIG_FILE, {"tasa": 0.0})
    return _cargar_json(CONFIG_FILE)


def guardar_config(tasa: float) -> None:
    _guardar_json(CONFIG_FILE, {"tasa": tasa})


def _cargar_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _guardar_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── CRUD de activos ──────────────────────────────────────────────────────────

def agregar_activo(simb: str, cantidad: float, precio: float, comision: float = 0, registro: float = 0, iva: float = 16) -> None:
    portafolio = cargar_portafolio()
    portafolio[simb.upper()] = {
        "cantidad": cantidad,
        "precio_promedio": precio,
        "comision": comision,
        "registro": registro,
        "iva": iva,
    }
    guardar_portafolio(portafolio)


def eliminar_activo(simb: str) -> bool:
    portafolio = cargar_portafolio()
    if simb.upper() in portafolio:
        del portafolio[simb.upper()]
        guardar_portafolio(portafolio)
        return True
    return False


def editar_activo(simb: str, cantidad: float, precio: float, comision: float = 0, registro: float = 0, iva: float = 16) -> bool:
    portafolio = cargar_portafolio()
    simb = simb.upper()
    if simb not in portafolio:
        return False
    portafolio[simb] = {
        "cantidad": cantidad,
        "precio_promedio": precio,
        "comision": comision,
        "registro": registro,
        "iva": iva,
    }
    guardar_portafolio(portafolio)
    return True


# ─── Cálculos ─────────────────────────────────────────────────────────────────

def calcular_fila(simb: str, datos: dict, precio_actual: float, total_mkt: float, tasa: float) -> dict:
    """Devuelve todos los valores calculados para una fila del portafolio."""
    cant  = _to_float(datos.get("cantidad"))
    prom  = _to_float(datos.get("precio_promedio"))
    com   = _to_float(datos.get("comision"))
    reg   = _to_float(datos.get("registro"))
    iva_p = _to_float(datos.get("iva", 16))

    costo_total = (cant * prom) + com + reg + (com * iva_p / 100)
    val_mkt     = cant * precio_actual
    ganancia    = val_mkt - costo_total
    gan_usd     = (ganancia / tasa) if tasa > 0 else 0
    rend        = (ganancia / costo_total * 100) if costo_total > 0 else 0
    peso        = (val_mkt / total_mkt * 100) if total_mkt > 0 else 0

    return {
        "simb":          simb,
        "cantidad":      cant,
        "precio_prom":   prom,
        "precio_actual": precio_actual,
        "costo_total":   costo_total,
        "val_mkt":       val_mkt,
        "ganancia":      ganancia,
        "gan_usd":       gan_usd,
        "rend_pct":      rend,
        "peso_pct":      peso,
    }


def resumen_portafolio(portafolio: dict, datos_bolsa: list, tasa: float) -> dict:
    """Calcula totales globales del portafolio."""
    mapa = {item["COD_SIMB"]: item for item in datos_bolsa}

    total_inv = 0.0
    total_mkt = 0.0

    for simb, d in portafolio.items():
        cant  = _to_float(d.get("cantidad"))
        prom  = _to_float(d.get("precio_promedio"))
        com   = _to_float(d.get("comision"))
        reg   = _to_float(d.get("registro"))
        iva_p = _to_float(d.get("iva", 16))

        precio_actual = _to_float(mapa.get(simb, {}).get("PRECIO") or prom)
        total_inv += (cant * prom) + com + reg + (com * iva_p / 100)
        total_mkt += cant * precio_actual

    gan_bs  = total_mkt - total_inv
    rend    = (gan_bs / total_inv * 100) if total_inv > 0 else 0
    gan_usd = (gan_bs / tasa) if tasa > 0 else 0

    return {
        "total_inv": total_inv,
        "total_mkt": total_mkt,
        "gan_bs":    gan_bs,
        "gan_usd":   gan_usd,
        "rend":      rend,
    }
