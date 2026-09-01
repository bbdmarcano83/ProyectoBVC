"""Caracas Bull V5 hybrid philosophy overlay.

V5 preserves V3 market/risk measurements, adds a fundamental gate and requires
market confirmation. A price drop alone never improves a V5 signal.
"""
from __future__ import annotations
from typing import Any

from services.fundamentals_v5 import enrich_fundamental_scores
from services.fundamental_sources_v5 import get_source, source_audit_summary
from services.investment_vehicle_v5 import enrich_investment_vehicles

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
    if pullback: reasons.append("ruta pullback: corrección + estabilización + confirmación")
    if leader: reasons.append("ruta líder: momentum 20/60 positivo + confirmación")
    return pullback, leader, reasons


def _v5_signal(row: dict) -> tuple[str, list[str]]:
    reasons: list[str] = []
    fundamental = row.get("fundamental_score_v5"); coverage = _n(row.get("fundamental_coverage_v5"))
    if fundamental is None:
        return "TÉCNICO V3 · SIN FUNDAMENTALES", ["faltan fundamentales auditables; no se emite confirmación V5"]
    fscore = _n(fundamental); strength = _n(row.get("strength_score_v3")); opportunity = _n(row.get("opportunity_score_v3")); confidence = _n(row.get("confidence_score_v3")); risk = _n(row.get("risk_score_v3"), 100); quality_ok = bool(row.get("data_quality_ok_v3")); pullback, leader, route_reasons = _routes(row)
    if coverage < 50: return "FUNDAMENTALES INCOMPLETOS", [f"cobertura fundamental insuficiente ({coverage:.0f}%)"]
    if fscore < 45: return "DESCARTAR FUNDAMENTAL", ["calidad/valor/margen de seguridad insuficientes"]
    if fscore >= 60: reasons.append("filtro fundamental superado")
    if strength >= 70: reasons.append("fortaleza de mercado suficiente")
    if confidence >= 60: reasons.append("confianza de datos suficiente")
    if risk < 60: reasons.append("riesgo dentro del límite")
    if row.get("industry_type_v5") == "investment_vehicle": reasons.append("vehículo evaluado por NAV/patrimonio, rendimiento y distribuciones")
    reasons.extend(route_reasons)
    gates = fscore >= 60 and coverage >= 60 and confidence >= 60 and risk < 60 and quality_ok
    if gates and strength >= 70 and opportunity >= 60 and (pullback or leader): return "OPORTUNIDAD HÍBRIDA CONFIRMADA", reasons
    if fscore >= 60 and strength >= 55 and confidence >= 55 and risk < 70: return "PREPARAR ENTRADA", reasons or ["fundamentales favorables; falta confirmación completa"]
    if fscore >= 60: return "CANDIDATA FUNDAMENTAL", reasons or ["fundamentales favorables; mercado todavía no confirma"]
    return "OBSERVAR", reasons or ["sin ventaja suficiente"]


def apply_v5(rows: list[dict], metadata: dict | None = None) -> tuple[list[dict], dict]:
    metadata = dict(metadata or {})
    symbols = [str(r.get("simbolo") or "").upper() for r in rows if r.get("simbolo")]
    source_audit = source_audit_summary(symbols)
    rows, fmeta = enrich_fundamental_scores(rows)
    rows, vehicle_meta = enrich_investment_vehicles(rows)
    confirmed = 0; with_fundamentals = 0
    for row in rows:
        src = get_source(str(row.get("simbolo") or ""))
        row["fundamental_source_registered_v5"] = bool(src)
        row["fundamental_source_confidence_v5"] = src.get("confidence", 0) if src else 0
        row["fundamental_source_status_v5"] = src.get("status", "unmapped") if src else "unmapped"
        if src and not row.get("industry_type_v5"):
            row["industry_type_v5"] = src.get("industry_type")
        fundamental = row.get("fundamental_score_v5")
        if fundamental is None:
            row["philosophy_score_v5"] = None
        else:
            with_fundamentals += 1
            row["philosophy_score_v5"] = _clamp(_n(fundamental)*0.40 + _n(row.get("strength_score_v3"))*0.25 + _n(row.get("opportunity_score_v3"))*0.15 + _n(row.get("confidence_score_v3"))*0.10 + (100.0-_n(row.get("risk_score_v3"),100.0))*0.10)
        stage, explain = _v5_signal(row)
        row["signal_stage_v5"] = stage; row["explain_v5"] = explain; row["philosophy_v5"] = "Caracas Bull: valor/calidad por tipo de emisor + Momentum/Confirmación"
        if stage == "OPORTUNIDAD HÍBRIDA CONFIRMADA": confirmed += 1
    global _LAST_V5_MAP
    _LAST_V5_MAP = {str(r.get("simbolo")): dict(r) for r in rows if r.get("simbolo")}
    metadata["engine_version"] = "V5-HYBRID"
    metadata["v5"] = {"fundamentals":fmeta,"investment_vehicles":vehicle_meta,"source_audit":source_audit,"rows_with_fundamentals":with_fundamentals,"confirmed_opportunities":confirmed,"principles":["Greenblatt: negocio bueno + valoración atractiva para operativas no financieras","Graham: margen de seguridad y solidez financiera","Buffett: calidad, rentabilidad y generación de caja sostenibles","Vehículos: NAV/patrimonio + rentabilidad + distribuciones + consistencia","Momentum: el mercado debe confirmar; no se compra una caída por caer"],"routes":["quality_pullback","market_leader"]}
    return rows, metadata


def get_last_scoring_map_v5() -> dict[str, dict]:
    return {k: dict(v) for k, v in _LAST_V5_MAP.items()}
