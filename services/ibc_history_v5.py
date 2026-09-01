"""Fuente de historia IBC para benchmark V5.

No inventa niveles del índice. Inicialmente carga una serie JSON explícita desde
`IBC_HISTORY_V5_JSON` o `IBC_HISTORY_V5_PATH`. El formato esperado es una lista
de objetos con fecha y cierre. Esto permite backfill auditable desde BVC antes
de habilitar una descarga automática estable.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def load_ibc_history() -> tuple[list[dict], dict]:
    raw = os.getenv("IBC_HISTORY_V5_JSON", "").strip()
    source = "none"
    if raw:
        source = "env:IBC_HISTORY_V5_JSON"
    else:
        path = os.getenv("IBC_HISTORY_V5_PATH", "").strip()
        if path:
            p = Path(path)
            if p.exists() and p.is_file():
                raw = p.read_text(encoding="utf-8")
                source = f"file:{p.name}"
    if not raw:
        return [], {"available": False, "source": source, "reason": "sin_historia_ibc"}
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return [], {"available": False, "source": source, "reason": "invalid_json"}
    if isinstance(payload, dict):
        payload = payload.get("points") or payload.get("history") or []
    if not isinstance(payload, list):
        return [], {"available": False, "source": source, "reason": "invalid_shape"}
    points = [p for p in payload if isinstance(p, dict)]
    return points, {"available": bool(points), "source": source, "count": len(points)}
