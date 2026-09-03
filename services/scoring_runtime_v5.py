"""Runtime compatibility helpers for Caracas Bull V5 scoring.

V3 fields remain available for auditability, but when V5 is active the public
legacy ``total`` field must represent the active Caracas Bull philosophy score.
This keeps older API/UI consumers aligned without destroying ``score_v3``.
"""
from __future__ import annotations

from typing import Any


def _number(value: Any, default: float = -1.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def activate_v5_runtime(rows: list[dict], metadata: dict | None = None) -> tuple[list[dict], dict]:
    """Expose and rank by the active V5 philosophy score.

    Contract:
    - ``score_v3`` remains untouched and is the V3 audit score.
    - ``philosophy_score_v5`` remains the canonical V5 score.
    - ``total`` is the backwards-compatible *active* score seen by legacy
      templates/routes while V5 is enabled.
    - rows are ordered by V5 score, never by the pre-overlay V3 order.
    - missing V5 scores sort last; they are not silently converted to zero.
    """
    metadata = dict(metadata or {})

    for row in rows:
        score = row.get("philosophy_score_v5")
        row["ranking_score_v5"] = score
        row["active_score_field"] = "philosophy_score_v5"
        if score is not None:
            row["total"] = score

    rows.sort(key=lambda row: _number(row.get("philosophy_score_v5")), reverse=True)

    metadata["active_score_field"] = "philosophy_score_v5"
    metadata["ranking_engine"] = "V5-HYBRID"
    if isinstance(metadata.get("v5"), dict):
        metadata["v5"] = dict(metadata["v5"])
        metadata["v5"]["active_score_field"] = "philosophy_score_v5"
        metadata["v5"]["ranking_order"] = "philosophy_score_v5_desc"

    return rows, metadata
