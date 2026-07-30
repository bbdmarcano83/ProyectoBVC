"""
Motor de Scoring BVC — Rotación Sectorial
Evalúa los 16 títulos del IBC en 4 dimensiones:
  Rendimiento (40pts), Liquidez (25pts), Dinamismo (20pts), Tendencia (15pts)
"""

from services.bvc import obtener_historico, obtener_datos_bvc, obtener_tasa_bcv, _to_float

# ── Universo IBC vigente desde 09-Mar-2026 ─────────────────────────────────
IBC_UNIVERSE = [
    {"simbolo": "BPV",   "nombre": "Banco Provincial",        "sector": "Financiero", "ibc": True},
    {"simbolo": "BNC",   "nombre": "Banco Nal. Crédito",      "sector": "Financiero", "ibc": True},
    {"simbolo": "BVCC",  "nombre": "Bolsa de Caracas",        "sector": "Financiero", "ibc": True},
    {"simbolo": "BVL",   "nombre": "Banco de Venezuela",      "sector": "Financiero", "ibc": True},
    {"simbolo": "MVZ.A", "nombre": "Mercantil A",             "sector": "Financiero", "ibc": True},
    {"simbolo": "ABC.A", "nombre": "Bancaribe A",             "sector": "Financiero", "ibc": True},
    {"simbolo": "MVZ.B", "nombre": "Mercantil B",             "sector": "Financiero", "ibc": True},
    {"simbolo": "RST",   "nombre": "Ron Santa Teresa",        "sector": "Industrial", "ibc": True},
    {"simbolo": "RST.B", "nombre": "Ron Sta Teresa B",        "sector": "Industrial", "ibc": True},
    {"simbolo": "TDV.D", "nombre": "CANTV D",                 "sector": "Industrial", "ibc": True},
    {"simbolo": "SVS",   "nombre": "Sivensa",                 "sector": "Industrial", "ibc": True},
    {"simbolo": "ENV",   "nombre": "Envases Venezolanos",     "sector": "Industrial", "ibc": True},
    {"simbolo": "CRM.A", "nombre": "Corimon A",               "sector": "Industrial", "ibc": True},
    {"simbolo": "DOM",   "nombre": "Domínguez & Cía.",        "sector": "Industrial", "ibc": True},
    {"simbolo": "MPA",   "nombre": "Manpa",                   "sector": "Industrial", "ibc": True},
    {"simbolo": "PIV.B", "nombre": "PIVCA B",                 "sector": "Industrial", "ibc": True},
]


def _calcular_dinamismo(historico: list[dict], window: int = 20) -> dict:
    """
    Distingue precio estable genuino de congelado artificial.
    Señal clave: spread_ratio > 5% con change_ratio < 15% = CONGELADO.
    """
    if len(historico) < 5:
        return {"score": 0, "label": "SIN DATOS", "color": "#888",
                "change_pct": 0, "spread_pct": 0, "avg_ops": 0}

    datos = historico[:window]  # ya vienen ordenados desc desde la BVC
    n = len(datos)

    # Extraer precios
    cierres = [_to_float(d.get("PRECIO_CIE", 0)) for d in datos]
    maximos = [_to_float(d.get("PRECIO_MAX", 0)) for d in datos]
    minimos = [_to_float(d.get("PRECIO_MIN", 0)) for d in datos]
    ops = [int(_to_float(d.get("TOT_OP_NEGOC", 0))) for d in datos]

    # Señal 1: días con cambio de cierre
    change_days = sum(1 for i in range(1, n) if abs(cierres[i] - cierres[i-1]) > 0.01)
    change_ratio = change_days / (n - 1) if n > 1 else 0

    # Señal 2: spread intradiario promedio vs cierre
    avg_close = sum(cierres) / n if n > 0 else 1
    avg_spread = sum(max(0, maximos[i] - minimos[i]) for i in range(n)) / n
    spread_ratio = avg_spread / avg_close if avg_close > 0 else 0

    # Señal 3: operaciones promedio
    avg_ops = sum(ops) / n if n > 0 else 0

    # Clasificación
    if change_ratio < 0.15 and spread_ratio > 0.05:
        result = {"score": 0, "label": "CONGELADO", "color": "#d03b3b"}
    elif change_ratio < 0.15 and avg_ops < 5:
        result = {"score": 0, "label": "MUERTO", "color": "#666"}
    elif change_ratio < 0.40 and spread_ratio > 0.08:
        result = {"score": 5, "label": "SOSPECHOSO", "color": "#c47a20"}
    elif change_ratio < 0.40:
        result = {"score": 12, "label": "ESTABLE", "color": "#6b8aad"}
    elif change_ratio >= 0.70:
        result = {"score": 20, "label": "MUY ACTIVO", "color": "#0F6E56"}
    else:
        result = {"score": 15, "label": "ACTIVO", "color": "#1baf7a"}

    result["change_pct"] = round(change_ratio * 100, 1)
    result["spread_pct"] = round(spread_ratio * 100, 1)
    result["avg_ops"] = round(avg_ops, 0)
    return result


def _calcular_rendimiento(historico: list[dict], devaluacion_pct: float) -> dict:
    """Retorno acumulado normalizado contra la devaluación BCV."""
    if len(historico) < 2:
        return {"score": 0, "ret_pct": 0}

    cierre_actual = _to_float(historico[0].get("PRECIO_CIE", 0))
    cierre_inicio = _to_float(historico[-1].get("PRECIO_CIE", 0))

    if cierre_inicio <= 0:
        return {"score": 0, "ret_pct": 0}

    ret_pct = ((cierre_actual / cierre_inicio) - 1) * 100
    ratio = ret_pct / devaluacion_pct if devaluacion_pct > 0 else 0
    score = min(40, max(0, ratio * 20))

    return {"score": round(score, 1), "ret_pct": round(ret_pct, 1)}


def _calcular_liquidez(historico: list[dict], window: int = 5) -> dict:
    """Volumen semanal en Bs."""
    if not historico:
        return {"score": 5, "vol_semanal": 0}

    datos = historico[:window]
    montos = [_to_float(d.get("TOT_MONTO_NEGOC", 0)) for d in datos]
    vol_semanal = sum(montos)

    if vol_semanal >= 10_000_000:
        score = 25
    elif vol_semanal >= 5_000_000:
        score = 20
    elif vol_semanal >= 2_000_000:
        score = 15
    elif vol_semanal >= 500_000:
        score = 10
    else:
        score = 5

    return {"score": score, "vol_semanal": round(vol_semanal, 0)}


def _calcular_tendencia(historico: list[dict], window: int = 20) -> dict:
    """Tendencia de los últimos N días."""
    if len(historico) < 5:
        return {"score": 10, "label": "SIN DATOS", "trend": "stable"}

    datos = historico[:window]
    cierre_reciente = _to_float(datos[0].get("PRECIO_CIE", 0))
    cierre_inicio = _to_float(datos[-1].get("PRECIO_CIE", 0))

    if cierre_inicio <= 0:
        return {"score": 10, "label": "SIN DATOS", "trend": "stable"}

    cambio_pct = ((cierre_reciente / cierre_inicio) - 1) * 100

    if cambio_pct > 10:
        return {"score": 15, "label": "SUBIENDO", "trend": "up"}
    elif cambio_pct > 0:
        return {"score": 12, "label": "LEVE ALZA", "trend": "up"}
    elif cambio_pct > -5:
        return {"score": 10, "label": "ESTABLE", "trend": "stable"}
    elif cambio_pct > -15:
        return {"score": 5, "label": "BAJANDO", "trend": "down"}
    else:
        return {"score": 0, "label": "CRASH", "trend": "crash"}


def _determinar_accion(score: int) -> dict:
    """Acción recomendada según score total."""
    if score >= 75:
        return {"label": "Core", "color": "#0F6E56", "bg": "rgba(27,175,122,0.12)"}
    elif score >= 50:
        return {"label": "Satélite", "color": "#185FA5", "bg": "rgba(42,120,214,0.12)"}
    elif score >= 30:
        return {"label": "Observar", "color": "#854F0B", "bg": "rgba(237,161,0,0.12)"}
    else:
        return {"label": "Vender", "color": "#d03b3b", "bg": "rgba(208,59,59,0.12)"}


async def calcular_scoring_completo(devaluacion_pct: float = 148.0) -> list[dict]:
    """
    Calcula el score de los 16 títulos del IBC.
    Llama a la API de la BVC para obtener datos frescos.
    """
    resultados = []

    for titulo in IBC_UNIVERSE:
        simbolo = titulo["simbolo"]
        try:
            historico = await obtener_historico(simbolo)
        except Exception as e:
            print(f"[Scoring] Error obteniendo {simbolo}: {e}")
            historico = []

        rend = _calcular_rendimiento(historico, devaluacion_pct)
        liq = _calcular_liquidez(historico)
        din = _calcular_dinamismo(historico)
        tend = _calcular_tendencia(historico)

        total = round(rend["score"] + liq["score"] + din["score"] + tend["score"])
        accion = _determinar_accion(total)

        resultados.append({
            "simbolo": simbolo,
            "nombre": titulo["nombre"],
            "sector": titulo["sector"],
            "ibc": titulo["ibc"],
            # Scores individuales
            "rend_score": rend["score"],
            "rend_pct": rend["ret_pct"],
            "liq_score": liq["score"],
            "liq_vol": liq["vol_semanal"],
            "din_score": din["score"],
            "din_label": din["label"],
            "din_color": din["color"],
            "din_change_pct": din["change_pct"],
            "din_spread_pct": din["spread_pct"],
            "din_avg_ops": din["avg_ops"],
            "tend_score": tend["score"],
            "tend_label": tend["label"],
            "tend_trend": tend["trend"],
            # Total
            "total": total,
            "accion": accion,
            # Precio actual
            "precio": _to_float(historico[0].get("PRECIO_CIE", 0)) if historico else 0,
        })

    # Ordenar por score descendente
    resultados.sort(key=lambda x: x["total"], reverse=True)

    return resultados
