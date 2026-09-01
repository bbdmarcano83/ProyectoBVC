"""Caracas Bull V5 hybrid philosophy overlay.

V5 does not replace V3 market/risk measurements. It adds a fundamental gate
and combines it with confirmation/timing. A price drop alone never improves a
V5 signal: pullbacks require stabilization/reacceleration and volume/price
confirmation. Leaders can qualify without a pullback when multi-horizon
momentum remains positive.
"""
from __future__ import annotations

from typing import Any

from services.fundamentals_v5 import enrich_fundamental_scores


def _n(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def _clamp(v: float) -> float:
    return round(max(0.0, min(100.0, v)), 1)


def _routes(row: dict) -> tuple[bool, bool, list[str]]:
    h = row.get("history_v3", {}) or {}
    drop = _n(row.get("caida_pct"))
    m5 = _n(h.get("momentum_5d_pct"))
    m20 = _n(h.get("momentum_20d_pct"))
    m60 = _n(h.get("momentum_60d_pct"))
    accel = _n(h.get("momentum_accel"))
    pv = _n(h.get("price_volume_confirmation"))
    strength = _n(row.get("strength_score_v3"))

    # Route A: quality pullback. Falling is not enough; it must stabilize.
    pullback_zone = -20.0 <= drop <= -3.0
    stabilization = accel > 0 or m5 > 0
    pullback = pullback_zone and stabilization and pv >= 60 and m20 > -10

    # Route B: leader/momentum. No pullback requirement.
    leader = m20 > 0 and m60 > 0 and strength >= 75 and pv >= 60

    reasons: list[str] = []
    if pullback:
        reasons.append("ruta pullback: corrección + estabilización + confirmación")
    if leader:
        reasons.append("ruta líder: momentum 20/60 positivo + confirmación")
    return pullback, leader, reasons


def _v5_signal(row: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    fundamental = row.get("fundamental_score_v5")
    coverage = _n(row.get("fundamental_coverage_v5"))
    if fundamental is None:
        return "TÉCNICO V3 · SIN FUNDAMENTALES", ["faltan fundamentales auditables; no se emite confirmación V5"]

    fscore = _n(fundamental)
    strength = _n(row.get("strength_score_v3"))
    opportunity = _n(row.get("opportunity_score_v3"))
    confidence = _n(row.get("confidence_score_v3"))
    risk = _n(row.get("risk_score_v3"), 100)
    quality_ok = bool(row.get("data_quality_ok_v3"))
    pullback, leader, route_reasons = _routes(row)

    if coverage < 50:
        return "FUNDAMENTALES INCOMPLETOS", [f"cobertura fundamental insuficiente ({coverage:.0f}%)"]
    if fscore < 45:
        return "DESCARTAR FUNDAMENTAL", ["calidad/valor/margen de seguridad insuficientes"]
    if fscore >= 60:
        reasons.append("filtro fundamental superado")
    if strength >= 70:
        reasons.append("fortaleza de mercado suficiente")
    if confidence >= 60:
        reasons.append("confianza de datos suficiente")
    if risk < 60:
        reasons.append("riesgo dentro del límite")
    reasons.extend(route_reasons)

    gates = fscore >= 60 and coverage >= 60 and confidence >= 60 and risk < 60 and quality_ok
    if gates and strength >= 70 and opportunity >= 60 and (pullback or leader):
        return "OPORTUNIDAD HÍBRIDA CONFIRMADA", reasons
    if fscore >= 60 and strength >= 55 and confidence >= 55 and risk < 70:
        return "PREPARAR ENTRADA", reasons or ["fundamentales favorables; falta confirmación completa"]
    if fscore >= 60:
        return "CANDIDATA FUNDAMENTAL", reasons or ["fundamentales favorables; mercado todavía no confirma"]
    return "OBSERVAR", reasons or ["sin ventaja suficiente"]


def apply_v5(rows: list[dict], metadata: dict | None = None) -> tuple[list[dict], dict]:
    """Overlay the unified philosophy without destroying V3 fields."""
    metadata = dict(metadata or {})
    rows, fmeta = enrich_fundamental_scores(rows)

    confirmed = 0
    with_fundamentals = 0
    for row in rows:
        fundamental = row.get("fundamental_score_v5")
        if fundamental is None:
            row["philosophy_score_v5"] = None
        else:
            with_fundamentals += 1
            row["philosophy_score_v5"] = _clamp(
                _n(fundamental) * 0.40
                + _n(row.get("strength_score_v3")) * 0.25
                + _n(row.get("opportunity_score_v3")) * 0.15
                + _n(row.get("confidence_score_v3")) * 0.10
                + (100.0 - _n(row.get("risk_score_v3"), 100.0)) * 0.10
            )

        stage, explain = _v5_signal(row)
        row["signal_stage_v5"] = stage
        row["explain_v5"] = explain
        row["philosophy_v5"] = "Caracas Bull: Greenblatt + Graham + Buffett + Momentum/Confirmación"
        if stage == "OPORTUNIDAD HÍBRIDA CONFIRMADA":
            confirmed += 1

    metadata["engine_version"] = "V5-HYBRID"
    metadata["v5"] = {
        "fundamentals": fmeta,
        "rows_with_fundamentals": with_fundamentals,
        "confirmed_opportunities": confirmed,
        "principles": [
            "Greenblatt: negocio bueno + valoración atractiva",
            "Graham: margen de seguridad y solidez financiera",
            "Buffett: calidad, rentabilidad y generación de caja sostenibles",
            "Momentum: el mercado debe confirmar; no se compra una caída por caer",
        ],
        "routes": ["quality_pullback", "market_leader"],
    }
    return rows, metadata
