"""Scoring Engine V3 — foundation / shadow mode.

V3 separa cuatro preguntas que el score V2 mezcla:
- QUALITY / CONFIDENCE: ¿los datos permiten confiar en la señal?
- STRENGTH: ¿el activo muestra fortaleza relativa frente al universo BVC?
- OPPORTUNITY: ¿el punto de entrada es atractivo ahora?
- RISK: ¿qué tan peligroso es entrar ahora?

La primera fase consume el resultado V2 ya calculado y NO vuelve a consultar BVC.
Esto permite comparar V2/V3 sobre exactamente el mismo snapshot y evita carga
adicional en producción. No elimina ni renombra campos legacy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from services.scoring import calcular_scoring_completo as calcular_scoring_legacy


@dataclass(frozen=True)
class ScoringV3Policy:
    confidence_min: float = 70.0
    opportunity_confirmed_min: float = 70.0
    score_structural_min: float = 70.0
    compra_caida_min_pct: float = -20.0
    compra_caida_max_pct: float = -8.0
    score_alto_min: float = 75.0
    score_medio_min: float = 50.0
    score_bajo_min: float = 30.0


POLICY = ScoringV3Policy()


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _clamp(value: Any, low: float = 0.0, high: float = 100.0) -> float:
    return round(max(low, min(high, _num(value))), 1)


def _percentile_map(rows: Iterable[dict], field: str) -> dict[str, float]:
    """Percentil 0..100 por símbolo; empates reciben el mismo percentil."""
    pairs = [
        (str(r.get("simbolo", "")), _num(r.get(field)))
        for r in rows
        if r.get("simbolo")
    ]
    if not pairs:
        return {}
    values = sorted(v for _, v in pairs)
    n = len(values)
    if n == 1:
        return {pairs[0][0]: 100.0}

    result: dict[str, float] = {}
    for simbolo, value in pairs:
        below = sum(1 for x in values if x < value)
        equal = sum(1 for x in values if x == value)
        rank = below + (equal - 1) / 2
        result[simbolo] = round(rank / (n - 1) * 100, 1)
    return result


def _quality_flags(row: dict) -> list[str]:
    flags: list[str] = []
    dias = int(_num(row.get("dias_datos")))
    precio = _num(row.get("precio"))
    liq_vol = _num(row.get("liq_vol"))
    frecuencia = _num(row.get("din_change_pct"))
    spread = _num(row.get("din_spread_pct"))

    if not row.get("fecha_ultimo") or row.get("fecha_ultimo") == "N/A":
        flags.append("sin_fecha")
    if precio <= 0:
        flags.append("sin_precio")
    if dias < 5:
        flags.append("historial_insuficiente")
    elif dias < 20:
        flags.append("historial_corto")
    if liq_vol <= 0:
        flags.append("sin_liquidez")
    if frecuencia < 15:
        flags.append("negociacion_escasa")
    if spread > 12:
        flags.append("spread_extremo")
    if row.get("din_label") in {"CONGELADO", "MUERTO"}:
        flags.append("activo_no_operable")
    return flags


def _confidence_score(row: dict) -> float:
    """Confianza independiente del atractivo del activo."""
    dias = _num(row.get("dias_datos"))
    frecuencia = _num(row.get("din_change_pct"))
    spread = _num(row.get("din_spread_pct"))
    avg_ops = _num(row.get("din_avg_ops"))
    liq = _num(row.get("liq_score"))

    history_component = min(100.0, dias / 60.0 * 100.0)
    frequency_component = min(100.0, frecuencia)
    operations_component = min(100.0, avg_ops / 20.0 * 100.0)
    liquidity_component = min(100.0, liq / 25.0 * 100.0)
    spread_component = max(0.0, 100.0 - max(0.0, spread - 2.0) * 8.0)

    score = (
        history_component * 0.25
        + frequency_component * 0.20
        + operations_component * 0.15
        + liquidity_component * 0.25
        + spread_component * 0.15
    )

    # Quality gates duros: un activo no debe tener alta confianza sólo por
    # puntuar bien en componentes parciales.
    flags = _quality_flags(row)
    if "sin_precio" in flags or "activo_no_operable" in flags:
        score = min(score, 25.0)
    elif "historial_insuficiente" in flags or "sin_liquidez" in flags:
        score = min(score, 45.0)
    return _clamp(score)


def _risk_score(row: dict, liquidity_percentile: float) -> float:
    """100 = riesgo alto; 0 = riesgo bajo."""
    caida = abs(min(0.0, _num(row.get("caida_pct"))))
    spread = max(0.0, _num(row.get("din_spread_pct")))
    frecuencia = _num(row.get("din_change_pct"))

    drawdown_risk = min(100.0, caida / 35.0 * 100.0)
    spread_risk = min(100.0, spread / 15.0 * 100.0)
    inactivity_risk = max(0.0, 100.0 - min(100.0, frecuencia))
    liquidity_risk = max(0.0, 100.0 - liquidity_percentile)

    risk = (
        drawdown_risk * 0.30
        + spread_risk * 0.25
        + inactivity_risk * 0.20
        + liquidity_risk * 0.25
    )
    if row.get("din_label") in {"CONGELADO", "MUERTO"}:
        risk = max(risk, 90.0)
    if row.get("tend_trend") == "crash":
        risk = max(risk, 85.0)
    return _clamp(risk)


def _strength_score(
    row: dict,
    return_percentile: float,
    liquidity_percentile: float,
    activity_percentile: float,
) -> float:
    """Fortaleza relativa cross-sectional, no timing de entrada."""
    trend_component = min(100.0, _num(row.get("tend_score")) / 15.0 * 100.0)
    legacy_component = _clamp(row.get("total"))
    return _clamp(
        return_percentile * 0.35
        + liquidity_percentile * 0.20
        + activity_percentile * 0.15
        + trend_component * 0.15
        + legacy_component * 0.15
    )


def _opportunity_score(row: dict, strength: float, confidence: float, risk: float) -> float:
    """Timing de entrada separado de la calidad estructural."""
    caida = _num(row.get("caida_pct"))

    # Zona preferida del plan: caída controlada entre -8% y -20%.
    if POLICY.compra_caida_min_pct <= caida <= POLICY.compra_caida_max_pct:
        drawdown_component = 100.0
    elif -25.0 <= caida < POLICY.compra_caida_min_pct:
        drawdown_component = 55.0
    elif POLICY.compra_caida_max_pct < caida <= -3.0:
        drawdown_component = 60.0
    elif caida < -25.0:
        drawdown_component = 20.0
    else:
        drawdown_component = 35.0

    risk_quality = max(0.0, 100.0 - risk)
    return _clamp(
        strength * 0.35
        + confidence * 0.25
        + drawdown_component * 0.25
        + risk_quality * 0.15
    )


def _signal_stage(row: dict) -> str:
    opportunity = _num(row.get("opportunity_score_v3"))
    confidence = _num(row.get("confidence_score_v3"))
    strength = _num(row.get("strength_score_v3"))
    risk = _num(row.get("risk_score_v3"))
    caida = _num(row.get("caida_pct"))

    controlled_drop = POLICY.compra_caida_min_pct <= caida <= POLICY.compra_caida_max_pct
    no_crash = row.get("tend_trend") != "crash"

    if (
        opportunity >= POLICY.opportunity_confirmed_min
        and confidence >= POLICY.confidence_min
        and strength >= POLICY.score_structural_min
        and risk < 60
        and controlled_drop
        and no_crash
        and row.get("data_quality_ok_v3")
    ):
        return "OPORTUNIDAD CONFIRMADA"
    if opportunity >= 60 and confidence >= 55 and strength >= 60 and no_crash:
        return "PREPARAR COMPRA"
    return "OBSERVAR"


def _score_class(score: float) -> str:
    if score >= POLICY.score_alto_min:
        return "alto"
    if score >= POLICY.score_medio_min:
        return "medio"
    if score >= POLICY.score_bajo_min:
        return "bajo"
    return "minimo"


def enriquecer_resultados_v3(resultados: list[dict], metadata: dict | None = None) -> tuple[list[dict], dict]:
    """Convierte un snapshot V2 ya calculado en snapshot V3 sin I/O adicional."""
    ret_pct = _percentile_map(resultados, "rend_pct")
    liq_pct = _percentile_map(resultados, "liq_vol")
    activity_pct = _percentile_map(resultados, "din_avg_ops")

    enriched: list[dict] = []
    for row in resultados:
        out = dict(row)
        simbolo = str(out.get("simbolo", ""))
        confidence = _confidence_score(out)
        risk = _risk_score(out, liq_pct.get(simbolo, 0.0))
        strength = _strength_score(
            out,
            ret_pct.get(simbolo, 0.0),
            liq_pct.get(simbolo, 0.0),
            activity_pct.get(simbolo, 0.0),
        )
        opportunity = _opportunity_score(out, strength, confidence, risk)
        flags = _quality_flags(out)

        out.update(
            {
                "engine_version": "v3-shadow-foundation",
                "legacy_score_v2": _clamp(out.get("total")),
                "return_percentile_v3": ret_pct.get(simbolo, 0.0),
                "liquidity_percentile_v3": liq_pct.get(simbolo, 0.0),
                "activity_percentile_v3": activity_pct.get(simbolo, 0.0),
                "confidence_score_v3": confidence,
                "strength_score_v3": strength,
                "opportunity_score_v3": opportunity,
                "risk_score_v3": risk,
                "quality_flags_v3": flags,
                "data_quality_ok_v3": len(flags) == 0,
            }
        )
        out["score_v3"] = _clamp(strength * 0.55 + opportunity * 0.25 + confidence * 0.20)
        out["score_class_v3"] = _score_class(out["score_v3"])
        out["signal_stage_v3"] = _signal_stage(out)
        out["señal_compra_v3"] = out["signal_stage_v3"] == "OPORTUNIDAD CONFIRMADA"
        enriched.append(out)

    enriched.sort(key=lambda x: x.get("score_v3", 0), reverse=True)

    meta = dict(metadata or {})
    meta.update(
        {
            "engine_version": "v3-shadow-foundation",
            "v3_mode": "same-snapshot-no-extra-io",
            "quality_issues": sum(1 for r in enriched if not r["data_quality_ok_v3"]),
            "confirmed_opportunities": sum(1 for r in enriched if r["señal_compra_v3"]),
            "policy": {
                "confidence_min": POLICY.confidence_min,
                "opportunity_confirmed_min": POLICY.opportunity_confirmed_min,
                "score_structural_min": POLICY.score_structural_min,
                "controlled_drawdown": [POLICY.compra_caida_min_pct, POLICY.compra_caida_max_pct],
            },
        }
    )
    return enriched, meta


def comparar_v2_v3(v2: list[dict], v3: list[dict]) -> dict:
    """Resumen compacto para observabilidad del shadow mode."""
    v3_map = {r.get("simbolo"): r for r in v3}
    deltas = []
    changed_signals = 0
    for old in v2:
        new = v3_map.get(old.get("simbolo"))
        if not new:
            continue
        deltas.append(_num(new.get("score_v3")) - _num(old.get("total")))
        if bool(old.get("señal_compra")) != bool(new.get("señal_compra_v3")):
            changed_signals += 1

    return {
        "symbols_compared": len(deltas),
        "avg_score_delta": round(sum(deltas) / len(deltas), 2) if deltas else 0.0,
        "max_abs_score_delta": round(max((abs(d) for d in deltas), default=0.0), 2),
        "changed_buy_signals": changed_signals,
    }


async def calcular_scoring_completo_v3(
    devaluacion_pct: float | None = None,
) -> tuple[list[dict], float, dict]:
    resultados, devaluacion, metadata = await calcular_scoring_legacy(devaluacion_pct)
    enriched, meta = enriquecer_resultados_v3(resultados, metadata)
    return enriched, devaluacion, meta
