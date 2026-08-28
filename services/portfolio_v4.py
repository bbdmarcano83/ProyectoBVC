"""Portfolio Engine V4.

Analítica adicional y compatible para el portafolio actual. No persiste ni
modifica posiciones; opera exclusivamente sobre las filas ya calculadas por
services.portafolio, por lo que puede activarse gradualmente sin migraciones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PortfolioV4Policy:
    concentracion_alta_pct: float = 35.0
    concentracion_media_pct: float = 20.0
    toma_ganancia_pct: float = 50.0
    perdida_revisar_pct: float = -20.0


POLICY = PortfolioV4Policy()


def _f(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def analizar_portafolio_v4(filas: Iterable[dict]) -> dict:
    rows = [dict(row) for row in filas]
    if not rows:
        return {
            "engine_version": "v4",
            "posiciones": 0,
            "concentracion_max_pct": 0.0,
            "riesgo_concentracion": "sin_posiciones",
            "ganadores": 0,
            "perdedores": 0,
            "candidatos_toma_ganancia": [],
            "candidatos_revision": [],
            "herfindahl": 0.0,
        }

    pesos = [max(0.0, _f(r.get("peso_pct"))) for r in rows]
    max_peso = max(pesos, default=0.0)
    hhi = sum((p / 100.0) ** 2 for p in pesos)

    if max_peso >= POLICY.concentracion_alta_pct:
        riesgo = "alto"
    elif max_peso >= POLICY.concentracion_media_pct:
        riesgo = "medio"
    else:
        riesgo = "bajo"

    candidatos_toma = []
    candidatos_revision = []
    for row in rows:
        rendimiento = _f(row.get("rend_pct"))
        simbolo = row.get("simb", "")
        if rendimiento >= POLICY.toma_ganancia_pct:
            candidatos_toma.append({"simbolo": simbolo, "rend_pct": round(rendimiento, 2)})
        if rendimiento <= POLICY.perdida_revisar_pct:
            candidatos_revision.append({"simbolo": simbolo, "rend_pct": round(rendimiento, 2)})

    return {
        "engine_version": "v4",
        "posiciones": len(rows),
        "concentracion_max_pct": round(max_peso, 2),
        "riesgo_concentracion": riesgo,
        "ganadores": sum(1 for r in rows if _f(r.get("rend_pct")) > 0),
        "perdedores": sum(1 for r in rows if _f(r.get("rend_pct")) < 0),
        "candidatos_toma_ganancia": candidatos_toma,
        "candidatos_revision": candidatos_revision,
        "herfindahl": round(hhi, 4),
    }


def enriquecer_resumen_v4(resumen: dict, filas: Iterable[dict]) -> dict:
    out = dict(resumen or {})
    out["portfolio_v4"] = analizar_portafolio_v4(filas)
    return out
