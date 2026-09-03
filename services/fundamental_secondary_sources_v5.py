"""Registro curado de fuentes secundarias admisibles para fundamentales V5.

Una fuente secundaria sólo entra como nivel B si está asociada explícitamente al
símbolo y host auditado aquí. Este registro no convierte la fuente en certificada:
Emisor/BVC/SUNAVAL continúan siendo nivel A y tienen precedencia absoluta.
"""
from __future__ import annotations

from copy import deepcopy
from urllib.parse import urlparse

SECONDARY_SOURCE_REGISTRY: dict[str, list[dict]] = {
    # MANPA: reproducción/sindicación de la publicación financiera auditada BVC.
    "MPA": [
        {
            "name": "MarketScreener/Public Technologies",
            "hosts": ["marketscreener.com"],
            "confidence": 70,
            "route": "syndicated_market_disclosure",
            "start_urls": [
                "https://es.marketscreener.com/noticias/corp-industrial-de-energia-c-a-saca-02-junio-2026-manufacturas-de-papel-c-a-manpa-s-a-c-a-y-ce7f5ddede8bf125",
            ],
        },
    ],
    # Cerámica Carabobo: reproducciones de convocatorias/resultados y estados.
    "CCR": [
        {
            "name": "MarketScreener/Public Technologies",
            "hosts": ["marketscreener.com"],
            "confidence": 70,
            "route": "syndicated_market_disclosure",
            "start_urls": [
                "https://es.marketscreener.com/cotizacion/accion/CERAMICA-CARABOBO-S-A-C-A-45418390/noticia/",
            ],
        },
        {
            "name": "Publicnow",
            "hosts": ["publicnow.com"],
            "confidence": 65,
            "route": "syndicated_market_disclosure",
            "start_urls": [],
        },
        {
            "name": "World Trading Casa de Bolsa",
            "hosts": ["wtcasadebolsa.com"],
            "confidence": 65,
            "route": "broker_market_disclosure",
            "start_urls": [
                "https://wtcasadebolsa.com/ceramica-carabobo-s-a-c-a-asamblea-general-extraordinaria-de-accionistas-a-celebrarse-el-12-de-junio-de-2025/",
            ],
        },
    ],
    # Montesco/Montesco Capital Global: reproducción de información financiera BVC.
    "MTC.B": [
        {
            "name": "MarketScreener/Public Technologies",
            "hosts": ["marketscreener.com"],
            "confidence": 70,
            "route": "syndicated_market_disclosure",
            "start_urls": [
                "https://es.marketscreener.com/cotizacion/accion/CORP-INDUSTRIAL-DE-ENERGI-20702651/noticia-comunicados/",
            ],
        },
    ],
    # Grupo Mantra: prospecto reproducido por una casa de bolsa venezolana.
    "GMC.B": [
        {
            "name": "Acciona Valores Casa de Bolsa",
            "hosts": ["accionavalores.com"],
            "confidence": 70,
            "route": "broker_prospectus_repository",
            "start_urls": [
                "https://www.accionavalores.com/assets/PROSPECTO-GRUPO-MANTRA.pdf",
            ],
        },
    ],
}


def _host(url: str) -> str:
    return (urlparse(str(url or "").strip()).hostname or "").lower().strip(".").removeprefix("www.")


def _host_matches(target: str, registered: str) -> bool:
    key = str(registered or "").lower().strip(".").removeprefix("www.")
    return bool(target and key) and (target == key or target.endswith("." + key))


def secondary_source_for_url(symbol: str, url: str) -> dict | None:
    symbol = str(symbol or "").upper().strip()
    target = _host(url)
    if not target:
        return None
    for source in SECONDARY_SOURCE_REGISTRY.get(symbol, []):
        if any(_host_matches(target, host) for host in source.get("hosts", [])):
            return deepcopy(source)
    return None


def secondary_start_urls(symbol: str) -> list[dict]:
    symbol = str(symbol or "").upper().strip()
    out: list[dict] = []
    for source in SECONDARY_SOURCE_REGISTRY.get(symbol, []):
        for url in source.get("start_urls", []):
            out.append({
                "url": str(url),
                "source_name": source.get("name"),
                "route": source.get("route"),
                "confidence": int(source.get("confidence") or 0),
            })
    return out
