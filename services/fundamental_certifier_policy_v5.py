"""Política de procedencia documental para fundamentales V5.

Jerarquía de evidencia:
A) certificada por emisor registrado, BVC o SUNAVAL;
B) secundaria HTTPS trazable para un emisor registrado.

La evidencia secundaria puede alimentar el fundamental, pero nunca desplaza a
una fuente certificada. Si existe evidencia A, prevalece siempre. Los conflictos
entre autoridades certificadas siguen fallando cerrado. Los conflictos entre
fuentes secundarias tampoco se resuelven por heurística: quedan pendientes hasta
que exista una única cifra reconciliable.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from services.fundamental_sources_v5 import get_source, source_url_allowed

CERTIFIER_POLICY_VERSION = "v5.3-tiered-fundamental-evidence"
CERTIFIERS = ("issuer", "bvc", "sunaval")
BVC_HOSTS = ("bolsadecaracas.com",)
SUNAVAL_HOSTS = ("sunaval.gob.ve",)
CERTIFIED_CONFIDENCE = 100
SECONDARY_CONFIDENCE = 60


def _host(url: str) -> str:
    return (urlparse(str(url or "").strip()).hostname or "").lower().strip(".")


def _https(url: str) -> bool:
    return urlparse(str(url or "").strip()).scheme.lower() == "https"


def _matches(host: str, domains: tuple[str, ...]) -> bool:
    key = host.removeprefix("www.")
    return any(key == d.removeprefix("www.") or key.endswith("." + d.removeprefix("www.")) for d in domains)


def certify_fundamental_source(symbol: str, url: str) -> dict:
    """Clasifica exclusivamente si una fuente es certificada nivel A."""
    symbol = str(symbol or "").upper().strip()
    source = get_source(symbol)
    host = _host(url)
    base = {
        "valid": False,
        "symbol": symbol,
        "url": str(url or "").strip(),
        "host": host or None,
        "certifier": None,
        "policy_version": CERTIFIER_POLICY_VERSION,
        "allowed_certifiers": list(CERTIFIERS),
        "evidence_tier": None,
        "evidence_confidence": 0,
    }
    if not source:
        return {**base, "reason": "symbol_not_registered"}
    if not _https(url) or not host:
        return {**base, "reason": "https_required"}

    if _matches(host, BVC_HOSTS):
        return {
            **base, "valid": True, "certifier": "bvc", "reason": None,
            "route": "market_authority", "evidence_tier": "A_CERTIFIED",
            "evidence_confidence": CERTIFIED_CONFIDENCE,
        }
    if _matches(host, SUNAVAL_HOSTS):
        return {
            **base, "valid": True, "certifier": "sunaval", "reason": None,
            "route": "regulator", "evidence_tier": "A_CERTIFIED",
            "evidence_confidence": CERTIFIED_CONFIDENCE,
        }
    if str(source.get("source_type") or "") == "issuer_official" and source_url_allowed(symbol, url):
        return {
            **base, "valid": True, "certifier": "issuer", "reason": None,
            "route": "registered_issuer_or_document_host", "evidence_tier": "A_CERTIFIED",
            "evidence_confidence": CERTIFIED_CONFIDENCE,
        }

    return {**base, "reason": "source_not_certified_by_issuer_bvc_or_sunaval"}


def classify_fundamental_source(symbol: str, url: str) -> dict:
    """Clasifica una fuente como nivel A certificado o nivel B secundario.

    Sólo símbolos registrados y URLs HTTPS son admisibles. Nivel B es utilizable
    para scoring fundamental con menor confianza, pero queda explícitamente
    marcado como no certificado.
    """
    certified = certify_fundamental_source(symbol, url)
    if certified.get("valid"):
        return {**certified, "admissible": True, "certified": True}

    symbol = str(symbol or "").upper().strip()
    host = _host(url)
    if not get_source(symbol):
        return {**certified, "admissible": False, "certified": False}
    if not _https(url) or not host:
        return {**certified, "admissible": False, "certified": False}

    return {
        **certified,
        "admissible": True,
        "certified": False,
        "reason": None,
        "route": "secondary_https",
        "evidence_tier": "B_SECONDARY",
        "evidence_confidence": SECONDARY_CONFIDENCE,
    }


def resolve_certified_evidence(symbol: str, candidates: list[dict[str, Any]]) -> dict:
    """Resuelve evidencia con precedencia A > B y conflicto fail-closed."""
    certified: list[dict[str, Any]] = []
    secondary: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for raw in candidates or []:
        item = dict(raw or {})
        source_url = str(item.get("source_url") or "").strip()
        evidence = classify_fundamental_source(symbol, source_url)
        enriched = {**item, "certification": evidence}
        if evidence.get("certified"):
            certified.append(enriched)
        elif evidence.get("admissible"):
            secondary.append(enriched)
        else:
            rejected.append(enriched)

    if certified:
        first_value = certified[0].get("value")
        conflicts = [row for row in certified[1:] if row.get("value") != first_value]
        if conflicts:
            return {
                "valid": False,
                "reason": "certified_authority_conflict",
                "value": None,
                "certified": certified,
                "secondary": secondary,
                "rejected": rejected,
                "policy_version": CERTIFIER_POLICY_VERSION,
            }
        return {
            "valid": True,
            "reason": None,
            "value": first_value,
            "certified": certified,
            "secondary": secondary,
            "rejected": rejected,
            "certifiers": sorted({str(row["certification"].get("certifier")) for row in certified}),
            "evidence_tier": "A_CERTIFIED",
            "evidence_confidence": CERTIFIED_CONFIDENCE,
            "policy_version": CERTIFIER_POLICY_VERSION,
        }

    if secondary:
        values = {row.get("value") for row in secondary}
        if len(values) != 1:
            return {
                "valid": False,
                "reason": "secondary_evidence_conflict",
                "value": None,
                "certified": [],
                "secondary": secondary,
                "rejected": rejected,
                "policy_version": CERTIFIER_POLICY_VERSION,
            }
        return {
            "valid": True,
            "reason": None,
            "value": secondary[0].get("value"),
            "certified": [],
            "secondary": secondary,
            "rejected": rejected,
            "certifiers": [],
            "evidence_tier": "B_SECONDARY",
            "evidence_confidence": SECONDARY_CONFIDENCE,
            "policy_version": CERTIFIER_POLICY_VERSION,
        }

    return {
        "valid": False,
        "reason": "no_admissible_evidence",
        "value": None,
        "certified": [],
        "secondary": [],
        "rejected": rejected,
        "policy_version": CERTIFIER_POLICY_VERSION,
    }
