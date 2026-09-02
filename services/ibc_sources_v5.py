"""Jerarquía de fuentes para histórico IBC en Caracas Bull V5."""
from __future__ import annotations

IBC_SOURCE_POLICY = {
    "bvc_official": {
        "priority": 1,
        "confidence": 100,
        "official": True,
        "domains": ["bolsadecaracas.com", "market.bolsadecaracas.com"],
        "note": "Publicaciones/resúmenes oficiales de la Bolsa de Valores de Caracas.",
    },
    "bvc_republished": {
        "priority": 2,
        "confidence": 85,
        "official": False,
        "domains": ["contrapunto.com"],
        "note": "Publicaciones de terceros que citan cierres BVC; sólo fallback verificable.",
    },
    "secondary_history": {
        "priority": 3,
        "confidence": 75,
        "official": False,
        "domains": ["datosmacro.expansion.com"],
        "note": "Serie histórica secundaria para backfill; no sustituye BVC cuando existe punto oficial.",
    },
}


def classify_source(url: str) -> dict:
    value = str(url or "").lower()
    for source_type, cfg in sorted(IBC_SOURCE_POLICY.items(), key=lambda kv: kv[1]["priority"]):
        if any(domain in value for domain in cfg.get("domains", [])):
            return {"source_type": source_type, **cfg}
    return {
        "source_type": "unknown",
        "priority": 99,
        "confidence": 0,
        "official": False,
        "domains": [],
        "note": "Fuente IBC no registrada; no debe alimentar benchmark validado.",
    }


def prefer_point(existing: dict | None, candidate: dict) -> dict:
    """Selecciona el punto de mayor prioridad para una misma fecha."""
    if existing is None:
        return candidate
    a = classify_source(existing.get("source_url", ""))
    b = classify_source(candidate.get("source_url", ""))
    if b["priority"] < a["priority"]:
        return candidate
    return existing
