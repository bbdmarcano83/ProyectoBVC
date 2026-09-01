"""Runtime facade for ProyectoBVC scoring.

V3 remains the production baseline. V5 is an opt-in overlay that adds the
Caracas Bull unified philosophy (Greenblatt + Graham + Buffett + market
confirmation) without destroying V3 fields.

Rollback:
- SCORING_ENGINE_V5_ENABLED=false -> V3
- SCORING_ENGINE_V3_ENABLED=false -> V2
"""
from __future__ import annotations

import os

from services.scoring_v2 import *  # legacy helpers kept for compatibility
from services.scoring_v2 import calcular_scoring_completo as calcular_scoring_completo_v2


def _flag(name: str, default: str) -> bool:
    raw = os.environ.get(name, default)
    return raw.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _v3_enabled() -> bool:
    return _flag("SCORING_ENGINE_V3_ENABLED", "true")


def _v5_enabled() -> bool:
    # Deliberately opt-in until fundamental-source coverage is validated.
    return _flag("SCORING_ENGINE_V5_ENABLED", "false")


async def calcular_scoring_completo(devaluacion_pct: float | None = None):
    if not _v3_enabled():
        return await calcular_scoring_completo_v2(devaluacion_pct)

    from services.scoring_engine_v3 import calcular_scoring_completo as calcular_v3
    from services.scoring_postprocess import apply_sector_and_events

    rows, deval, metadata = await calcular_v3(devaluacion_pct)
    rows, metadata = apply_sector_and_events(rows, metadata)

    if _v5_enabled():
        from services.scoring_engine_v5 import apply_v5
        rows, metadata = apply_v5(rows, metadata)

    return rows, deval, metadata
