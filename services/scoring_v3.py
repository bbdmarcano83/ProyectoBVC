"""Scoring Engine V3.

Capa compatible sobre el motor v2 actual. Conserva el contrato de salida
(resultados, devaluacion, metadata) y añade normalización, quality gates y
metadata versionada. Se activa únicamente mediante feature flag en main.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.scoring import calcular_scoring_completo as calcular_scoring_legacy


@dataclass(frozen=True)
class ScoringV3Policy:
    compra_score_min: int = 65
    compra_liquidez_min: int = 15
    caida_oportunidad_pct: float = -15.0
    score_alto_min: int = 75
    score_medio_min: int = 50
    score_bajo_min: int = 30


POLICY = ScoringV3Policy()


def _clamp_score(value: Any) -> float:
    try:
        return round(max(0.0, min(100.0, float(value))), 1)
    except (TypeError, ValueError):
        return 0.0


def _quality_flags(row: dict) -> list[str]:
    flags: list[str] = []
    if not row.get("fecha_ultimo") or row.get("fecha_ultimo") == "N/A":
        flags.append("sin_fecha")
    if float(row.get("precio", 0) or 0) <= 0:
        flags.append("sin_precio")
    if int(row.get("dias_datos", 0) or 0) < 5:
        flags.append("historial_corto")
    if float(row.get("liq_vol", 0) or 0) <= 0:
        flags.append("sin_liquidez")
    return flags


def _clasificacion(score: float) -> str:
    if score >= POLICY.score_alto_min:
        return "alto"
    if score >= POLICY.score_medio_min:
        return "medio"
    if score >= POLICY.score_bajo_min:
        return "bajo"
    return "minimo"


def enriquecer_resultado(row: dict) -> dict:
    """Añade campos V3 sin eliminar ni renombrar campos heredados."""
    out = dict(row)
    total = _clamp_score(out.get("total"))
    quality = _quality_flags(out)

    out["total"] = total
    out["score_v3"] = total
    out["score_class_v3"] = _clasificacion(total)
    out["quality_flags_v3"] = quality
    out["data_quality_ok_v3"] = len(quality) == 0
    out["engine_version"] = "v3"

    caida = float(out.get("caida_pct", 0) or 0)
    liq_score = float(out.get("liq_score", 0) or 0)
    out["señal_compra_v3"] = bool(
        caida <= POLICY.caida_oportunidad_pct
        and total >= POLICY.compra_score_min
        and liq_score >= POLICY.compra_liquidez_min
        and out["data_quality_ok_v3"]
    )
    return out


async def calcular_scoring_completo_v3(
    devaluacion_pct: float | None = None,
) -> tuple[list[dict], float, dict]:
    resultados, devaluacion, metadata = await calcular_scoring_legacy(devaluacion_pct)
    enriched = [enriquecer_resultado(row) for row in resultados]
    enriched.sort(key=lambda x: x.get("score_v3", 0), reverse=True)

    meta = dict(metadata or {})
    meta.update(
        {
            "engine_version": "v3",
            "compatibility_mode": "legacy-v2-contract",
            "policy": {
                "compra_score_min": POLICY.compra_score_min,
                "compra_liquidez_min": POLICY.compra_liquidez_min,
                "caida_oportunidad_pct": POLICY.caida_oportunidad_pct,
            },
            "quality_issues": sum(1 for r in enriched if not r["data_quality_ok_v3"]),
        }
    )
    return enriched, devaluacion, meta
