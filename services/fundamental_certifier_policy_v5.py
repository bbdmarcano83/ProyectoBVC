"""Política única de certificación documental para fundamentales V5.

Sólo tres actores pueden certificar un documento fundamental:
1) el emisor registrado;
2) la Bolsa de Valores de Caracas (BVC);
3) SUNAVAL.

CDN/hosts auxiliares pueden distribuir documentos del emisor únicamente cuando
están declarados expresamente en su registro auditable. Ninguna otra fuente
secundaria certifica fundamentales, aunque pueda servir para discovery.

Regla de precedencia: cualquier dato certificado prevalece sobre evidencia no
certificada. Si dos o más autoridades certificadas discrepan para la misma
magnitud/período, el sistema no inventa una jerarquía entre ellas: falla cerrado
y exige reconciliación con el documento primario.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from services.fundamental_sources_v5 import get_source, source_url_allowed

CERTIFIER_POLICY_VERSION = "v5.2-certified-data-precedence"
CERTIFIERS = ("issuer", "bvc", "sunaval")
BVC_HOSTS = ("bolsadecaracas.com",)
SUNAVAL_HOSTS = ("sunaval.gob.ve",)


def _host(url: str) -> str:
    return (urlparse(str(url or "").strip()).hostname or "").lower().strip(".")


def _https(url: str) -> bool:
    return urlparse(str(url or "").strip()).scheme.lower() == "https"


def _matches(host: str, domains: tuple[str, ...]) -> bool:
    key = host.removeprefix("www.")
    return any(key == d.removeprefix("www.") or key.endswith("." + d.removeprefix("www.")) for d in domains)


def certify_fundamental_source(symbol: str, url: str) -> dict:
    """Clasifica la autoridad certificadora y falla cerrado fuera del trío."""
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
    }
    if not source:
        return {**base, "reason": "symbol_not_registered"}
    if not _https(url) or not host:
        return {**base, "reason": "https_required"}

    # BVC y SUNAVAL son autoridades certificadoras por sí mismas para cualquier
    # emisor registrado; identidad y cifras siguen pasando parser/review/gates.
    if _matches(host, BVC_HOSTS):
        return {**base, "valid": True, "certifier": "bvc", "reason": None, "route": "market_authority"}
    if _matches(host, SUNAVAL_HOSTS):
        return {**base, "valid": True, "certifier": "sunaval", "reason": None, "route": "regulator"}

    # El emisor puede publicar en su dominio o en un CDN/document host declarado
    # expresamente en SOURCE_REGISTRY. Un HTTPS externo cualquiera no basta.
    if str(source.get("source_type") or "") == "issuer_official" and source_url_allowed(symbol, url):
        return {**base, "valid": True, "certifier": "issuer", "reason": None, "route": "registered_issuer_or_document_host"}

    return {**base, "reason": "source_not_certified_by_issuer_bvc_or_sunaval"}


def resolve_certified_evidence(symbol: str, candidates: list[dict[str, Any]]) -> dict:
    """Resuelve una magnitud dando precedencia absoluta a evidencia certificada.

    Cada candidato debe aportar ``value`` y ``source_url``. Los candidatos no
    certificados se conservan únicamente en ``rejected`` para auditoría y nunca
    pueden completar, reemplazar o desempatar un valor certificado.

    Si las fuentes certificadas coinciden exactamente en ``value``, el valor se
    acepta y se conserva la procedencia de todas ellas. Si discrepan, se bloquea
    la resolución con ``certified_authority_conflict``; BVC, SUNAVAL y emisor son
    autoridades válidas y el motor no debe escoger una cifra distinta por
    heurística, scraping secundario o score de confianza.
    """
    certified: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for raw in candidates or []:
        item = dict(raw or {})
        source_url = str(item.get("source_url") or "").strip()
        certification = certify_fundamental_source(symbol, source_url)
        enriched = {**item, "certification": certification}
        if certification.get("valid"):
            certified.append(enriched)
        else:
            rejected.append(enriched)

    if not certified:
        return {
            "valid": False,
            "reason": "no_certified_evidence",
            "value": None,
            "certified": [],
            "rejected": rejected,
            "policy_version": CERTIFIER_POLICY_VERSION,
        }

    first_value = certified[0].get("value")
    conflicts = [row for row in certified[1:] if row.get("value") != first_value]
    if conflicts:
        return {
            "valid": False,
            "reason": "certified_authority_conflict",
            "value": None,
            "certified": certified,
            "rejected": rejected,
            "policy_version": CERTIFIER_POLICY_VERSION,
        }

    return {
        "valid": True,
        "reason": None,
        "value": first_value,
        "certified": certified,
        "rejected": rejected,
        "certifiers": sorted({str(row["certification"].get("certifier")) for row in certified}),
        "policy_version": CERTIFIER_POLICY_VERSION,
    }
