"""
Motor de Scoring BVC — Rotación Sectorial v2
Evalúa los 16 títulos del IBC en 4 dimensiones:
  Rendimiento (40pts), Liquidez (25pts), Dinamismo (20pts), Tendencia (15pts)

Notas:
  - Rendimiento se calcula YTD (desde enero del año en curso)
  - La devaluación BCV se obtiene automáticamente
  - Liquidación en BVC es T+3 (3 días hábiles)
"""

from datetime import datetime, timedelta
from services.bvc import obtener_historico, obtener_datos_bvc, obtener_tasa_bcv, _to_float

# ── Títulos que conforman el IBC (para marcar la bandera) ─────────────────
IBC_SIMBOLOS = {
    "BPV", "BNC", "BVCC", "BVL", "MVZ.A", "ABC.A", "MVZ.B",
    "RST", "RST.B", "TDV.D", "SVS", "ENV", "CRM.A", "DOM", "MPA", "PIV.B",
}

# ── Tasa BCV de referencia al 01-Ene-2026 ──────────────────────────────────
# Usada para calcular devaluación YTD automáticamente
TASA_BCV_INICIO_2026 = 78.13  # Bs/USD al 01-Ene-2026 (post-reconversión)


def _parse_fecha_bvc(fecha_str: str) -> datetime | None:
    """Parsea fechas BVC como '29-JUL-26' o '15-JUN-26'."""
    meses = {
        "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AGO": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DIC": 12,
        "JAN": 1, "APR": 4, "AUG": 8,
    }
    try:
        parts = fecha_str.strip().split("-")
        dia = int(parts[0])
        mes = meses.get(parts[1].upper(), 0)
        anio = int(parts[2])
        if anio < 100:
            anio += 2000
        if mes == 0:
            return None
        return datetime(anio, mes, dia)
    except Exception:
        return None


def _filtrar_ytd(historico: list[dict]) -> list[dict]:
    """Filtra histórico para quedarse solo con datos del año en curso (YTD)."""
    anio_actual = datetime.now().year
    inicio_anio = datetime(anio_actual, 1, 1)

    ytd = []
    for d in historico:
        fecha = _parse_fecha_bvc(d.get("FEC", ""))
        if fecha and fecha >= inicio_anio:
            ytd.append(d)

    return ytd if len(ytd) >= 2 else historico[:120]


def _filtrar_periodo(historico: list[dict], dias: int = 30) -> list[dict]:
    """Filtra histórico para los últimos N días."""
    limite = datetime.now() - timedelta(days=dias)
    filtrado = []
    for d in historico:
        fecha = _parse_fecha_bvc(d.get("FEC", ""))
        if fecha and fecha >= limite:
            filtrado.append(d)
    return filtrado if len(filtrado) >= 2 else historico[:dias]


def _calcular_dinamismo(historico: list[dict], window: int = 20) -> dict:
    """
    Distingue precio estable genuino de congelado artificial.
    Señal clave: spread_ratio > 5% con change_ratio < 15% = CONGELADO.
    """
    if len(historico) < 5:
        return {"score": 0, "label": "SIN DATOS", "color": "#888",
                "change_pct": 0, "spread_pct": 0, "avg_ops": 0}

    datos = historico[:window]
    n = len(datos)

    cierres = [_to_float(d.get("PRECIO_CIE", 0)) for d in datos]
    maximos = [_to_float(d.get("PRECIO_MAX", 0)) for d in datos]
    minimos = [_to_float(d.get("PRECIO_MIN", 0)) for d in datos]
    ops = [int(_to_float(d.get("TOT_OP_NEGOC", 0))) for d in datos]

    change_days = sum(1 for i in range(1, n) if abs(cierres[i] - cierres[i-1]) > 0.01)
    change_ratio = change_days / (n - 1) if n > 1 else 0

    avg_close = sum(cierres) / n if n > 0 else 1
    avg_spread = sum(max(0, maximos[i] - minimos[i]) for i in range(n)) / n
    spread_ratio = avg_spread / avg_close if avg_close > 0 else 0

    avg_ops = sum(ops) / n if n > 0 else 0

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
    """
    Retorno YTD normalizado contra la devaluación BCV.
    
    Intenta calcular YTD. Si no hay suficientes datos,
    usa todo el histórico disponible como fallback.
    
    Nota BVC: liquidación T+3 (3 días hábiles para acreditar).
    """
    if len(historico) < 2:
        return {"score": 0, "ret_pct": 0, "periodo": "sin datos",
                "precio_actual": 0, "precio_inicio": 0, "dias_datos": 0}

    # Intentar YTD primero
    ytd = _filtrar_ytd(historico)

    # Fallback: si YTD tiene pocos datos, usar todo el histórico
    if len(ytd) < 5:
        datos = historico
        periodo = "completo"
    else:
        datos = ytd
        periodo = "ytd"

    # datos[0] = más reciente, datos[-1] = más antiguo del período
    cierre_actual = _to_float(datos[0].get("PRECIO_CIE", 0))
    cierre_inicio = _to_float(datos[-1].get("PRECIO_CIE", 0))

    # Fallback: si cierre es 0, intentar con apertura
    if cierre_actual <= 0:
        cierre_actual = _to_float(datos[0].get("PRECIO_APERT", 0))
    if cierre_inicio <= 0:
        cierre_inicio = _to_float(datos[-1].get("PRECIO_APERT", 0))

    if cierre_inicio <= 0 or cierre_actual <= 0:
        return {"score": 0, "ret_pct": 0, "periodo": periodo,
                "precio_actual": cierre_actual, "precio_inicio": cierre_inicio,
                "dias_datos": len(datos)}

    ret_pct = ((cierre_actual / cierre_inicio) - 1) * 100

    # Normalizar contra devaluación: ratio 1.0 = iguala al dólar
    ratio = ret_pct / devaluacion_pct if devaluacion_pct > 0 else 0
    score = min(40, max(0, ratio * 20))

    return {
        "score": round(score, 1),
        "ret_pct": round(ret_pct, 1),
        "periodo": periodo,
        "precio_actual": round(cierre_actual, 2),
        "precio_inicio": round(cierre_inicio, 2),
        "dias_datos": len(datos),
    }


def _calcular_liquidez(historico: list[dict], window: int = 5) -> dict:
    """Volumen semanal en Bs (últimos 5 días de trading)."""
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


def _calcular_tendencia(historico: list[dict]) -> dict:
    """Tendencia de los últimos 30 días."""
    reciente = _filtrar_periodo(historico, dias=30)

    if len(reciente) < 3:
        return {"score": 10, "label": "SIN DATOS", "trend": "stable"}

    cierre_hoy = _to_float(reciente[0].get("PRECIO_CIE", 0))
    cierre_30d = _to_float(reciente[-1].get("PRECIO_CIE", 0))

    if cierre_30d <= 0 or cierre_hoy <= 0:
        return {"score": 10, "label": "SIN DATOS", "trend": "stable"}

    cambio_pct = ((cierre_hoy / cierre_30d) - 1) * 100

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
    """Clasificación por score — NO es recomendación de inversión."""
    if score >= 75:
        return {"label": "Score alto", "color": "#0F6E56", "bg": "rgba(27,175,122,0.12)"}
    elif score >= 50:
        return {"label": "Score medio", "color": "#185FA5", "bg": "rgba(42,120,214,0.12)"}
    elif score >= 30:
        return {"label": "Score bajo", "color": "#854F0B", "bg": "rgba(237,161,0,0.12)"}
    else:
        return {"label": "Score mínimo", "color": "#d03b3b", "bg": "rgba(208,59,59,0.12)"}


async def _obtener_devaluacion_ytd() -> float:
    """Calcula la devaluación BCV acumulada YTD automáticamente."""
    try:
        tasa_actual = await obtener_tasa_bcv()
        if tasa_actual > 0 and TASA_BCV_INICIO_2026 > 0:
            return round(((tasa_actual / TASA_BCV_INICIO_2026) - 1) * 100, 1)
    except Exception as e:
        print(f"[Scoring] Error obteniendo tasa BCV: {e}")
    return 148.0  # fallback


async def calcular_scoring_completo(devaluacion_pct: float | None = None) -> tuple[list[dict], float, dict]:
    """
    Calcula el score de TODAS las acciones listadas en la BVC.
    Trae la lista directamente de la pizarra en vivo.

    Returns:
        (resultados, devaluacion_usada, metadata)
    """
    if devaluacion_pct is None or devaluacion_pct <= 0:
        devaluacion_pct = await _obtener_devaluacion_ytd()

    # Traer TODAS las acciones de la pizarra BVC
    pizarra = await obtener_datos_bvc()
    if not pizarra:
        return [], devaluacion_pct, {"error": "No se pudo obtener la pizarra BVC"}

    resultados = []
    errores = []

    for item in pizarra:
        simbolo = item.get("COD_SIMB", "")
        nombre = item.get("DESC_SIMB", simbolo)
        if not simbolo:
            continue

        try:
            historico = await obtener_historico(simbolo)
            if not historico:
                errores.append(simbolo)
                continue
        except Exception as e:
            print(f"[Scoring] Error obteniendo {simbolo}: {e}")
            errores.append(simbolo)
            continue

        rend = _calcular_rendimiento(historico, devaluacion_pct)
        liq = _calcular_liquidez(historico)
        din = _calcular_dinamismo(historico)
        tend = _calcular_tendencia(historico)

        total = round(rend["score"] + liq["score"] + din["score"] + tend["score"])
        accion = _determinar_accion(total)

        precio_actual = _to_float(historico[0].get("PRECIO_CIE", 0))
        fecha_ultimo = historico[0].get("FEC", "N/A")
        ytd_data = _filtrar_ytd(historico)
        dias_ytd = len(ytd_data)

        resultados.append({
            "simbolo": simbolo,
            "nombre": nombre,
            "sector": item.get("TIPO_INDI_SECTOR", "—"),
            "ibc": simbolo in IBC_SIMBOLOS,
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
            "total": total,
            "accion_label": accion["label"],
            "accion_color": accion["color"],
            "accion_bg": accion["bg"],
            "precio": precio_actual,
            "fecha_ultimo": fecha_ultimo,
            "dias_ytd": dias_ytd,
            "precio_actual": rend.get("precio_actual", 0),
            "precio_inicio": rend.get("precio_inicio", 0),
            "dias_datos": rend.get("dias_datos", 0),
            "periodo_rend": rend.get("periodo", ""),
        })

    resultados.sort(key=lambda x: x["total"], reverse=True)

    metadata = {
        "fecha_calculo": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "titulos_total": len(pizarra),
        "titulos_ok": len(resultados),
        "titulos_ibc": sum(1 for r in resultados if r["ibc"]),
        "titulos_error": errores,
        "nota_t3": "Liquidación T+3: al comprar/vender, la operación se acredita en 3 días hábiles.",
    }

    return resultados, devaluacion_pct, metadata
