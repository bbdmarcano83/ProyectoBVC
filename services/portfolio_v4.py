"""Portfolio Engine V4 — intelligence layer.

V4 no persiste ni modifica posiciones. Consume las filas ya calculadas por
services.portafolio y, opcionalmente, un mapa de scoring V3 por símbolo.
Esto permite activarlo en shadow mode sin migraciones ni cambios de UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class PortfolioV4Policy:
    concentracion_alta_pct: float = 35.0
    concentracion_media_pct: float = 20.0
    toma_ganancia_pct: float = 50.0
    perdida_revisar_pct: float = -20.0
    score_debil_max: float = 50.0


@dataclass(frozen=True)
class FeePolicy:
    """Modelo operativo alineado con la bitácora actual de ProyectoBVC."""
    corretaje_pct: float = 4.0
    iva_sobre_corretaje_pct: float = 16.0
    registro_pct: float = 0.1
    islr_venta_pct: float = 1.0

    def costo_compra_pct(self) -> float:
        return round(
            self.corretaje_pct
            + self.corretaje_pct * self.iva_sobre_corretaje_pct / 100.0
            + self.registro_pct,
            3,
        )

    def costo_venta_pct(self) -> float:
        return round(self.costo_compra_pct() + self.islr_venta_pct, 3)

    def friccion_rotacion_pct(self) -> float:
        return round(self.costo_venta_pct() + self.costo_compra_pct(), 3)


POLICY = PortfolioV4Policy()
FEES = FeePolicy()


def _f(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, value)), 1)


def evaluar_rotacion_v4(
    simbolo_actual: str,
    score_actual: float,
    simbolo_candidato: str,
    score_candidato: float,
    ventaja_bruta_esperada_pct: float,
    fee_policy: FeePolicy = FEES,
) -> dict:
    """Evalúa si una rotación conserva ventaja después de fricción.

    `ventaja_bruta_esperada_pct` debe provenir de un modelo/backtest; no se
    infiere artificialmente a partir de la diferencia de score.
    """
    friccion = fee_policy.friccion_rotacion_pct()
    ventaja_neta = _f(ventaja_bruta_esperada_pct) - friccion
    return {
        "origen": simbolo_actual,
        "destino": simbolo_candidato,
        "score_origen": round(_f(score_actual), 1),
        "score_destino": round(_f(score_candidato), 1),
        "delta_score": round(_f(score_candidato) - _f(score_actual), 1),
        "ventaja_bruta_esperada_pct": round(_f(ventaja_bruta_esperada_pct), 2),
        "friccion_rotacion_pct": friccion,
        "ventaja_neta_esperada_pct": round(ventaja_neta, 2),
        "rotacion_economicamente_valida": ventaja_neta > 0,
    }


def analizar_portafolio_v4(
    filas: Iterable[dict],
    scoring_por_simbolo: Mapping[str, dict] | None = None,
) -> dict:
    rows = [dict(row) for row in filas]
    scoring = scoring_por_simbolo or {}

    if not rows:
        return {
            "engine_version": "v4-shadow-foundation",
            "posiciones": 0,
            "salud_cartera": 0.0,
            "concentracion_max_pct": 0.0,
            "concentracion_top3_pct": 0.0,
            "riesgo_concentracion": "sin_posiciones",
            "ganadores": 0,
            "perdedores": 0,
            "score_ponderado": None,
            "confidence_ponderado": None,
            "risk_ponderado": None,
            "capital_score_debil_pct": 0.0,
            "capital_en_alerta_pct": 0.0,
            "candidatos_toma_ganancia": [],
            "candidatos_revision": [],
            "herfindahl": 0.0,
            "friccion_rotacion_pct": FEES.friccion_rotacion_pct(),
        }

    pesos = [max(0.0, _f(r.get("peso_pct"))) for r in rows]
    total_peso = sum(pesos) or 100.0
    max_peso = max(pesos, default=0.0)
    top3 = sum(sorted(pesos, reverse=True)[:3])
    hhi = sum((p / 100.0) ** 2 for p in pesos)

    if max_peso >= POLICY.concentracion_alta_pct:
        riesgo_concentracion = "alto"
    elif max_peso >= POLICY.concentracion_media_pct:
        riesgo_concentracion = "medio"
    else:
        riesgo_concentracion = "bajo"

    candidatos_toma = []
    candidatos_revision = []
    weighted_score = 0.0
    weighted_confidence = 0.0
    weighted_risk = 0.0
    scoring_weight = 0.0
    capital_debil = 0.0
    capital_alerta = 0.0

    for row in rows:
        simbolo = str(row.get("simb", ""))
        peso = max(0.0, _f(row.get("peso_pct")))
        rendimiento = _f(row.get("rend_pct"))
        score_row = scoring.get(simbolo, {})
        score = score_row.get("score_v3")
        confidence = score_row.get("confidence_score_v3")
        risk = score_row.get("risk_score_v3")
        signal_stage = score_row.get("signal_stage_v3")

        if rendimiento >= POLICY.toma_ganancia_pct:
            candidatos_toma.append(
                {
                    "simbolo": simbolo,
                    "rend_pct": round(rendimiento, 2),
                    "peso_pct": round(peso, 2),
                }
            )
        if rendimiento <= POLICY.perdida_revisar_pct:
            candidatos_revision.append(
                {
                    "simbolo": simbolo,
                    "rend_pct": round(rendimiento, 2),
                    "motivo": "perdida_relevante",
                }
            )

        if score is not None:
            weighted_score += _f(score) * peso
            weighted_confidence += _f(confidence) * peso
            weighted_risk += _f(risk) * peso
            scoring_weight += peso
            if _f(score) < POLICY.score_debil_max:
                capital_debil += peso
            if signal_stage == "OBSERVAR" and (_f(score) < POLICY.score_debil_max or _f(risk) >= 70):
                capital_alerta += peso

    score_ponderado = round(weighted_score / scoring_weight, 1) if scoring_weight else None
    confidence_ponderado = round(weighted_confidence / scoring_weight, 1) if scoring_weight else None
    risk_ponderado = round(weighted_risk / scoring_weight, 1) if scoring_weight else None

    # Salud: sólo se calcula plenamente si existe scoring V3. La concentración
    # siempre penaliza porque es observable desde el portafolio por sí solo.
    concentration_penalty = min(35.0, max(0.0, max_peso - 15.0) * 1.2)
    if score_ponderado is not None:
        health = (
            score_ponderado * 0.45
            + (confidence_ponderado or 0.0) * 0.25
            + max(0.0, 100.0 - (risk_ponderado or 0.0)) * 0.30
            - concentration_penalty
        )
        salud = _clamp(health)
    else:
        salud = _clamp(70.0 - concentration_penalty)

    return {
        "engine_version": "v4-shadow-foundation",
        "posiciones": len(rows),
        "salud_cartera": salud,
        "concentracion_max_pct": round(max_peso, 2),
        "concentracion_top3_pct": round(top3, 2),
        "riesgo_concentracion": riesgo_concentracion,
        "ganadores": sum(1 for r in rows if _f(r.get("rend_pct")) > 0),
        "perdedores": sum(1 for r in rows if _f(r.get("rend_pct")) < 0),
        "score_ponderado": score_ponderado,
        "confidence_ponderado": confidence_ponderado,
        "risk_ponderado": risk_ponderado,
        "capital_score_debil_pct": round(capital_debil / total_peso * 100.0, 1),
        "capital_en_alerta_pct": round(capital_alerta / total_peso * 100.0, 1),
        "candidatos_toma_ganancia": candidatos_toma,
        "candidatos_revision": candidatos_revision,
        "herfindahl": round(hhi, 4),
        "friccion_rotacion_pct": FEES.friccion_rotacion_pct(),
    }


def enriquecer_resumen_v4(
    resumen: dict,
    filas: Iterable[dict],
    scoring_por_simbolo: Mapping[str, dict] | None = None,
) -> dict:
    out = dict(resumen or {})
    out["portfolio_v4"] = analizar_portafolio_v4(filas, scoring_por_simbolo)
    return out
