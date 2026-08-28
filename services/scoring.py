"""Runtime facade for ProyectoBVC scoring.

V3 full/stateless is enabled by default on the upgrade branch because the app
is paused for migration. Rollback: SCORING_ENGINE_V3_ENABLED=false.
"""
from __future__ import annotations

import os

from services.scoring_v2 import *  # legacy helpers kept for compatibility
from services.scoring_v2 import calcular_scoring_completo as calcular_scoring_completo_v2


def _enabled() -> bool:
    raw = os.environ.get("SCORING_ENGINE_V3_ENABLED", "true")
    return raw.strip().lower() in {"1", "true", "yes", "on", "enabled"}


async def calcular_scoring_completo(devaluacion_pct: float | None = None):
    if not _enabled():
        return await calcular_scoring_completo_v2(devaluacion_pct)

    from services.scoring_engine_v3 import calcular_scoring_completo as calcular_v3
    from services.scoring_postprocess import apply_sector_and_events

    rows, deval, metadata = await calcular_v3(devaluacion_pct)
    rows, metadata = apply_sector_and_events(rows, metadata)
    return rows, deval, metadata
