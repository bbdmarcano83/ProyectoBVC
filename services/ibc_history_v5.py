"""Fuente de historia IBC para benchmark V5.

Carga una serie JSON explícita desde `IBC_HISTORY_V5_JSON` o
`IBC_HISTORY_V5_PATH`. Cuando los puntos incluyen `source_url`, deduplica por
fecha conservando la fuente de mayor prioridad (BVC oficial primero). Puntos
legacy sin source_url siguen siendo legibles para compatibilidad, pero quedan
marcados como no auditados en metadata.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime

from services.ibc_sources_v5 import classify_source, prefer_point


def _date_key(point: dict) -> str | None:
    raw = point.get("date") or point.get("fecha") or point.get("as_of")
    if not raw:
        return None
    s = str(raw).strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date().isoformat()
    except ValueError:
        # Soporta dd/mm/YYYY en backfills manuales provenientes de boletines.
        try:
            return datetime.strptime(str(raw).strip()[:10], "%d/%m/%Y").date().isoformat()
        except ValueError:
            return None


def _numeric_level(point: dict) -> float | None:
    raw = point.get("close") or point.get("cierre") or point.get("value") or point.get("nivel")
    if raw in (None, ""):
        return None
    try:
        if isinstance(raw, str):
            value = raw.strip().replace(".", "").replace(",", ".") if "," in raw else raw
        else:
            value = raw
        out = float(value)
        return out if out > 0 else None
    except (TypeError, ValueError):
        return None


def normalize_auditable_points(points: list[dict]) -> tuple[list[dict], dict]:
    by_date: dict[str, dict] = {}
    invalid = 0
    untrusted = 0
    legacy_without_source = 0
    for raw in points or []:
        if not isinstance(raw, dict):
            invalid += 1
            continue
        day = _date_key(raw)
        level = _numeric_level(raw)
        if not day or level is None:
            invalid += 1
            continue
        item = dict(raw)
        item["date"] = day
        item["close"] = level
        source_url = str(item.get("source_url") or "").strip()
        if source_url:
            trust = classify_source(source_url)
            item["source_type"] = trust["source_type"]
            item["source_confidence"] = trust["confidence"]
            item["source_official"] = trust["official"]
            if trust["confidence"] <= 0:
                untrusted += 1
                continue
        else:
            legacy_without_source += 1
            item["source_type"] = "legacy_manual"
            item["source_confidence"] = 0
            item["source_official"] = False

        existing = by_date.get(day)
        if existing is None:
            by_date[day] = item
        elif source_url and existing.get("source_url"):
            by_date[day] = prefer_point(existing, item)
        elif source_url and not existing.get("source_url"):
            by_date[day] = item
        # Si ambos carecen de source_url se conserva el primero para estabilidad.

    normalized = [by_date[k] for k in sorted(by_date)]
    audited = sum(1 for p in normalized if int(p.get("source_confidence") or 0) >= 75)
    official = sum(1 for p in normalized if p.get("source_official"))
    return normalized, {
        "invalid_points": invalid,
        "untrusted_points": untrusted,
        "legacy_without_source": legacy_without_source,
        "audited_points": audited,
        "official_points": official,
    }


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
    points, audit = normalize_auditable_points(payload)
    return points, {
        "available": bool(points),
        "source": source,
        "count": len(points),
        **audit,
    }
