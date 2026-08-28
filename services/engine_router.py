"""Router de motores V3/V4.

Mantiene la decisión de rollout fuera de las rutas FastAPI. El caller entrega
el snapshot legacy ya calculado; el router nunca hace I/O externo.
"""

from __future__ import annotations

from services.feature_flags import (
    scoring_v3_enabled,
    scoring_v3_shadow_enabled,
    portfolio_v4_enabled,
    portfolio_v4_shadow_enabled,
)
from services.scoring_v3 import enriquecer_resultados_v3, comparar_v2_v3
from services.portfolio_v4 import enriquecer_resumen_v4


def route_scoring_snapshot(
    resultados_v2: list[dict],
    metadata_v2: dict | None = None,
) -> tuple[list[dict], dict, dict | None]:
    """Retorna (resultados_visibles, metadata_visible, shadow_report).

    - Sin flags: identidad exacta V2.
    - SHADOW: identidad V2 + reporte comparativo interno.
    - ENABLED: V3 visible manteniendo campos legacy dentro de cada fila.
    """
    metadata = dict(metadata_v2 or {})

    if scoring_v3_enabled():
        v3, meta_v3 = enriquecer_resultados_v3(resultados_v2, metadata)
        return v3, meta_v3, comparar_v2_v3(resultados_v2, v3)

    if scoring_v3_shadow_enabled():
        v3, _ = enriquecer_resultados_v3(resultados_v2, metadata)
        return resultados_v2, metadata, comparar_v2_v3(resultados_v2, v3)

    return resultados_v2, metadata, None


def route_portfolio_summary(
    resumen_v3_legacy: dict,
    filas: list[dict],
    scoring_por_simbolo: dict[str, dict] | None = None,
) -> tuple[dict, dict | None]:
    """Retorna (resumen_visible, shadow_v4).

    En shadow mode el resumen visible permanece byte-for-byte equivalente a
    la estructura legacy entregada por el caller.
    """
    base = dict(resumen_v3_legacy or {})

    if portfolio_v4_enabled():
        enriched = enriquecer_resumen_v4(base, filas, scoring_por_simbolo)
        return enriched, enriched.get("portfolio_v4")

    if portfolio_v4_shadow_enabled():
        shadow = enriquecer_resumen_v4(base, filas, scoring_por_simbolo).get("portfolio_v4")
        return base, shadow

    return base, None
