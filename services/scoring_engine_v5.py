"""Caracas Bull V5 hybrid philosophy overlay.

V5 preserves V3 market/risk measurements and adds fundamentals when available.
Missing or technically invalid fundamentals never block a valid listed asset:
the philosophy score is renormalized over the available pillars. Fundamental
evidence can be tier A (issuer/BVC/SUNAVAL) or tier B (secondary); tier B is
usable with lower weight and full provenance.
"""
from __future__ import annotations
from typing import Any

from services.fundamentals_v5 import enrich_fundamental_scores
from services.fundamental_sources_v5 import get_source, source_audit_summary
from services.fundamental_certifier_policy_v5 import classify_fundamental_source
from services.investment_vehicle_v5 import enrich_investment_vehicles
from services.fundamental_trend_v5 import attach_fundamental_trends

_LAST_V5_MAP: dict[str, dict] = {}


def _n(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def _clamp(v: float) -> float:
    return round(max(0.0, min(100.0, v)), 1)


def _routes(row: dict) -> tuple[bool, bool, list[str]]:
    h = row.get("history_v3", {}) or {}
    drop = _n(row.get("caida_pct")); m5 = _n(h.get("momentum_5d_pct")); m20 = _n(h.get("momentum_20d_pct")); m60 = _n(h.get("momentum_60d_pct")); accel = _n(h.get("momentum_accel")); pv = _n(h.get("price_volume_confirmation")); strength = _n(row.get("strength_score_v3"))
    pullback = -20.0 <= drop <= -3.0 and (accel > 0 or m5 > 0) and pv >= 60 and m20 > -10
    leader = m20 > 0 and m60 > 0 and strength >= 75 and pv >= 60
    reasons: list[str] = []
    if pullback:
        reasons.append("ruta pullback: corrección + estabilización + confirmación")
    if leader:
        reasons.append("ruta líder: momentum 20/60 positivo + confirmación")
    return pullback, leader, reasons


def _fundamental_evidence(row: dict) -> dict:
    symbol = str(row.get("simbolo") or "").upper().strip()
    source_url = str(row.get("source_v5") or "").strip()
    if not source_url:
        return {
            "admissible": False,
            "certified": False,
            "evidence_tier": "NONE",
            "evidence_confidence": 0,
        }
    return classify_fundamental_source(symbol, source_url)


def _weighted_available(parts: list[tuple[float | None, float]]) -> tuple[float | None, float]:
    available = [(float(v), float(w)) for v, w in parts if v is not None and w > 0]
    if not available:
        return None, 0.0
    total = sum(w for _, w in available)
    score = sum(v * w for v, w in available) / total
    nominal = sum(float(w) for _, w in parts if w > 0)
    coverage = total / nominal * 100.0 if nominal > 0 else 0.0
    return _clamp(score), round(coverage, 1)


def _philosophy_score(row: dict) -> tuple[float | None, float]:
    """Renormalize over available pillars; missing fundamental is never zero."""
    fundamental = row.get("fundamental_score_v5")
    evidence_conf = _n(row.get("fundamental_evidence_confidence_v5"), 0.0) / 100.0
    fundamental_weight = 0.40 * max(0.0, min(1.0, evidence_conf)) if fundamental is not None else 0.0
    return _weighted_available([
        (_n(fundamental) if fundamental is not None else None, fundamental_weight),
        (_n(row.get("strength_score_v3")), 0.25),
        (_n(row.get("opportunity_score_v3")), 0.15),
        (_n(row.get("confidence_score_v3")), 0.10),
        (100.0 - _n(row.get("risk_score_v3"), 100.0), 0.10),
    ])


def _v5_signal(row: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    fundamental = row.get("fundamental_score_v5")
    coverage = _n(row.get("fundamental_coverage_v5"))
    strength = _n(row.get("strength_score_v3")); opportunity = _n(row.get("opportunity_score_v3")); confidence = _n(row.get("confidence_score_v3")); risk = _n(row.get("risk_score_v3"), 100); quality_ok = bool(row.get("data_quality_ok_v3")); pullback, leader, route_reasons = _routes(row)

    if fundamental is None:
        reasons.append("fundamental no disponible o pendiente; activo valorado con pilares de mercado/riesgo disponibles")
        reasons.extend(route_reasons)
        if quality_ok and confidence >= 60 and risk < 60 and strength >= 70 and opportunity >= 60 and (pullback or leader):
            return "OPORTUNIDAD DE MERCADO · SIN FUNDAMENTAL", reasons
        if quality_ok and strength >= 55 and confidence >= 55 and risk < 70:
            return "EVALUABLE · SIN FUNDAMENTAL", reasons
        return "OBSERVAR · SIN FUNDAMENTAL", reasons

    evidence_tier = str(row.get("fundamental_evidence_tier_v5") or "NONE")
    evidence_conf = _n(row.get("fundamental_evidence_confidence_v5"))
    if evidence_tier == "B_SECONDARY":
        reasons.append(f"fundamental de fuente secundaria trazable; confianza de evidencia {evidence_conf:.0f}%")
    elif evidence_tier == "A_CERTIFIED":
        reasons.append("fundamental certificado por emisor/BVC/SUNAVAL")

    if row.get("fx_valid_v5") is False:
        flags = row.get("fx_flags_v5") or []
        detail = ", ".join(str(x) for x in flags[:3]) if flags else "tasa BCV histórica incompleta"
        return "EVALUABLE · FUNDAMENTAL FX PENDIENTE", [f"normalización USD pendiente: {detail}"] + reasons

    fscore = _n(fundamental)
    if coverage < 50:
        return "EVALUABLE · FUNDAMENTAL INCOMPLETO", [f"cobertura fundamental insuficiente ({coverage:.0f}%)"] + reasons
    if fscore < 45:
        return "EVALUABLE · FUNDAMENTAL DÉBIL", ["calidad/valor/margen de seguridad insuficientes"] + reasons
    if fscore >= 60:
        reasons.append("filtro fundamental superado")
    if strength >= 70:
        reasons.append("fortaleza de mercado suficiente")
    if confidence >= 60:
        reasons.append("confianza de datos de mercado suficiente")
    if risk < 60:
        reasons.append("riesgo dentro del límite")
    if row.get("fx_valid_v5"):
        reasons.append("fundamentales normalizados a USD con FX histórico validado")
    trend = str(row.get("fundamental_trend_v5") or "")
    if trend == "MEJORANDO":
        reasons.append("tendencia fundamental USD mejorando")
    elif trend == "DETERIORANDO":
        reasons.append("tendencia fundamental USD deteriorándose")
    if row.get("industry_type_v5") == "investment_vehicle":
        reasons.append("vehículo evaluado por NAV/patrimonio, rendimiento y distribuciones")
    reasons.extend(route_reasons)

    gates = fscore >= 60 and coverage >= 60 and confidence >= 60 and risk < 60 and quality_ok and bool(row.get("fx_valid_v5"))
    if gates and strength >= 70 and opportunity >= 60 and (pullback or leader):
        return "OPORTUNIDAD HÍBRIDA CONFIRMADA", reasons
    if fscore >= 60 and strength >= 55 and confidence >= 55 and risk < 70:
        return "PREPARAR ENTRADA", reasons or ["fundamentales favorables; falta confirmación completa"]
    if fscore >= 60:
        return "CANDIDATA FUNDAMENTAL", reasons or ["fundamentales favorables; mercado todavía no confirma"]
    return "OBSERVAR", reasons or ["sin ventaja suficiente"]


def apply_v5(rows: list[dict], metadata: dict | None = None) -> tuple[list[dict], dict]:
    metadata = dict(metadata or {})
    symbols = [str(r.get("simbolo") or "").upper() for r in rows if r.get("simbolo")]
    source_audit = source_audit_summary(symbols)
    rows, fmeta = enrich_fundamental_scores(rows)
    rows, vehicle_meta = enrich_investment_vehicles(rows)
    rows, trend_meta = attach_fundamental_trends(rows)
    confirmed = 0; with_fundamentals = 0; without_fundamentals = 0; fx_pending = 0; secondary_fundamentals = 0

    for row in rows:
        src = get_source(str(row.get("simbolo") or ""))
        row["fundamental_source_registered_v5"] = bool(src)
        row["fundamental_source_registry_confidence_v5"] = src.get("confidence", 0) if src else 0
        row["fundamental_source_status_v5"] = src.get("status", "unmapped") if src else "unmapped"
        if src and not row.get("industry_type_v5"):
            row["industry_type_v5"] = src.get("industry_type")

        fundamental = row.get("fundamental_score_v5")
        if fundamental is None:
            without_fundamentals += 1
            row["fundamental_evidence_tier_v5"] = "NONE"
            row["fundamental_evidence_confidence_v5"] = 0
            row["fundamental_source_certified_v5"] = False
        else:
            with_fundamentals += 1
            evidence = _fundamental_evidence(row)
            row["fundamental_evidence_tier_v5"] = evidence.get("evidence_tier") or "NONE"
            row["fundamental_evidence_confidence_v5"] = int(evidence.get("evidence_confidence") or 0)
            row["fundamental_source_certified_v5"] = bool(evidence.get("certified"))
            if row["fundamental_evidence_tier_v5"] == "B_SECONDARY":
                secondary_fundamentals += 1

        philosophy, pillar_coverage = _philosophy_score(row)
        row["philosophy_score_v5"] = philosophy
        row["philosophy_pillar_coverage_v5"] = pillar_coverage
        row["asset_evaluable_v5"] = True

        stage, explain = _v5_signal(row)
        row["signal_stage_v5"] = stage
        row["explain_v5"] = explain
        row["philosophy_v5"] = "Caracas Bull: valor/calidad cuando existe + mercado/riesgo renormalizados + USD/BCV"
        if stage == "OPORTUNIDAD HÍBRIDA CONFIRMADA":
            confirmed += 1
        if "FX PENDIENTE" in stage:
            fx_pending += 1

    global _LAST_V5_MAP
    _LAST_V5_MAP = {str(r.get("simbolo")): dict(r) for r in rows if r.get("simbolo")}
    metadata["engine_version"] = "V5-HYBRID"
    metadata["v5"] = {
        "fundamentals": fmeta,
        "investment_vehicles": vehicle_meta,
        "fundamental_trend": trend_meta,
        "source_audit": source_audit,
        "rows_with_fundamentals": with_fundamentals,
        "rows_without_fundamentals": without_fundamentals,
        "rows_with_secondary_fundamentals": secondary_fundamentals,
        "fx_pending": fx_pending,
        "confirmed_opportunities": confirmed,
        "principles": [
            "Activos BVC válidos siguen siendo evaluables aunque no exista fundamental disponible",
            "Fuentes A: emisor/BVC/SUNAVAL; fuentes B: secundarias HTTPS trazables con menor confianza",
            "Precedencia: evidencia certificada siempre prevalece sobre secundaria",
            "Greenblatt: negocio bueno + valoración atractiva para operativas no financieras",
            "Graham: margen de seguridad y solidez financiera",
            "Buffett: calidad, rentabilidad y generación de caja sostenibles",
            "Vehículos: NAV/patrimonio + rentabilidad + distribuciones + consistencia",
            "FX: estados venezolanos se normalizan a USD con BCV histórico; nunca con la tasa de hoy",
            "Fundamental Trend: evolución multi-período sólo con cifras comparables en USD",
            "Momentum: el mercado debe confirmar; no se compra una caída por caer",
        ],
        "routes": ["quality_pullback", "market_leader"],
    }
    return rows, metadata


def get_last_scoring_map_v5() -> dict[str, dict]:
    return {k: dict(v) for k, v in _LAST_V5_MAP.items()}
