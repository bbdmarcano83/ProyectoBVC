"""Portfolio overlay for the Caracas Bull V5 philosophy.

It does not trade or mutate holdings. It translates the V5 scoring state into
portfolio review actions while preserving V4 concentration/fee controls.
"""
from __future__ import annotations

from typing import Iterable, Mapping


def _f(v, default=0.0):
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def analizar_portafolio_v5(filas: Iterable[dict], scoring: Mapping[str, dict] | None = None) -> dict:
    scoring = scoring or {}
    actions: list[dict] = []
    for row in filas:
        symbol = str(row.get("simb") or "")
        score = scoring.get(symbol, {})
        stage = str(score.get("signal_stage_v5") or "")
        v5 = score.get("philosophy_score_v5")
        fundamental = score.get("fundamental_score_v5")
        risk = _f(score.get("risk_score_v3"), 100)
        strength = _f(score.get("strength_score_v3"))
        rend = _f(row.get("rend_pct"))
        peso = _f(row.get("peso_pct"))

        action = "MANTENER / OBSERVAR"
        reason = "sin gatillo V5 de cartera"
        if stage == "DESCARTAR FUNDAMENTAL" or (fundamental is not None and _f(fundamental) < 45):
            action, reason = "REVISAR / ROTAR", "tesis fundamental débil"
        elif risk >= 70:
            action, reason = "REDUCIR / REVISAR", "riesgo elevado"
        elif stage == "OPORTUNIDAD HÍBRIDA CONFIRMADA" and strength >= 75 and rend > 0 and peso < 25:
            action, reason = "CANDIDATA A AUMENTAR", "mercado confirma y la posición no está concentrada"
        elif stage in {"CANDIDATA FUNDAMENTAL", "PREPARAR ENTRADA"}:
            action, reason = "MANTENER / ESPERAR", "fundamentales favorables; falta confirmación completa"

        actions.append({
            "simbolo": symbol,
            "accion_v5": action,
            "motivo_v5": reason,
            "score_v5": v5,
            "fundamental_v5": fundamental,
            "riesgo_v3": risk,
            "rend_pct": round(rend, 2),
            "peso_pct": round(peso, 2),
        })

    return {
        "engine_version": "v5-portfolio-overlay",
        "acciones": actions,
        "candidatas_a_aumentar": [a for a in actions if a["accion_v5"] == "CANDIDATA A AUMENTAR"],
        "revisar_rotar": [a for a in actions if "ROTAR" in a["accion_v5"] or "REDUCIR" in a["accion_v5"]],
        "note": "Aumentar/rotar es analítico; la rotación real sigue sujeta a ventaja neta de fees/backtest V4.",
    }
