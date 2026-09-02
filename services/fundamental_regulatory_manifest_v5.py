"""Fuentes regulatorias/mercado verificadas para ampliar fundamentales V5.

Este manifiesto complementa el backfill principal sin inventar cifras. Cada
entrada debe apuntar a un documento oficial del emisor, BVC o SUNAVAL y conserva
la evidencia de por qué la fuente es admisible. La persistencia sigue pasando
por parser, ecuación contable, FX histórico y collector fail-closed.
"""
from __future__ import annotations

from urllib.parse import urlparse

AUTHORITATIVE_MARKET_HOSTS = {
    "bolsadecaracas.com": {"authority": "BVC", "confidence": 100},
    "sunaval.gob.ve": {"authority": "SUNAVAL", "confidence": 100},
}


def classify_authoritative_url(url: str) -> dict:
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme.lower() != "https":
        return {"official": False, "confidence": 0, "authority": None, "host": parsed.hostname}
    host = (parsed.hostname or "").lower().strip(".")
    host_key = host.removeprefix("www.")
    for domain, meta in AUTHORITATIVE_MARKET_HOSTS.items():
        key = domain.removeprefix("www.")
        if host_key == key or host_key.endswith("." + key):
            return {"official": True, "confidence": int(meta["confidence"]), "authority": meta["authority"], "host": host}
    return {"official": False, "confidence": 0, "authority": None, "host": host}


REGULATORY_BACKFILL_V5 = {
    "PIV.B": {
        "issuer": "PIVCA Promotora de Inversiones y Valores, C.A.",
        "industry_type": "non_financial",
        "documents": [
            {
                "fiscal_period": "FY2025",
                "as_of": "2025-12-31",
                "audited": True,
                "document_type": "annual_audited",
                "currency": "VES",
                "monetary_basis": "nominal_ves",
                "value_multiplier": 1,
                "url": "https://pivca.com/wp-content/uploads/2.-Informe-de-Auditoria-PIVCA-Valores-20252.pdf",
                "discovery_url": "https://pivca.com/prospectos/",
                "regulatory_evidence": {
                    "sunaval_registration": "Nº 219 de Providencia de fecha 16/12/2020",
                    "statement_unit": "Expresado en Bolívares Nominales",
                    "statement_period": "31/12/2025 comparativo con 31/12/2024",
                },
            }
        ],
    }
}


def regulatory_manifest_summary() -> dict:
    docs = sum(len(item.get("documents", [])) for item in REGULATORY_BACKFILL_V5.values())
    return {"issuers": len(REGULATORY_BACKFILL_V5), "documents": docs, "symbols": sorted(REGULATORY_BACKFILL_V5)}
