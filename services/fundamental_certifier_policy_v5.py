"""Política única de certificación documental para fundamentales V5.

Sólo tres actores pueden certificar un documento fundamental:
1) el emisor registrado;
2) la Bolsa de Valores de Caracas (BVC);
3) SUNAVAL.

CDN/hosts auxiliares pueden distribuir documentos del emisor únicamente cuando
están declarados expresamente en su registro auditable. Ninguna otra fuente
secundaria certifica fundamentales, aunque pueda servir para discovery.
"""
from __future__ import annotations

from urllib.parse import urlparse

from services.fundamental_sources_v5 import get_source, source_url_allowed

CERTIFIER_POLICY_VERSION = "v5.1-three-authorities"
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
