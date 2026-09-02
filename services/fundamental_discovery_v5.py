"""Descubrimiento seguro de documentos fundamentales V5.

Sólo navega la página oficial registrada para el símbolo y devuelve enlaces
candidatos del mismo host (o subdominio). No extrae cifras ni persiste nada.
"""
from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from services.fundamental_sources_v5 import get_source

KEYWORDS = (
    "estado", "financ", "audit", "informe", "gestion", "gestión", "trimes",
    "semes", "anual", "balance", "accionista", "inversionista", "prospecto",
    "resultado", "memoria", "report", "financial", "annual", "quarter",
)


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = None
            self._text = []


def _host_allowed(candidate_url: str, registered_url: str) -> bool:
    try:
        c = (urlparse(candidate_url).hostname or "").lower().strip(".")
        r = (urlparse(registered_url).hostname or "").lower().strip(".")
    except Exception:
        return False
    if not c or not r:
        return False
    return c == r or c.endswith("." + r) or r.endswith("." + c)


def _is_candidate(url: str, text: str) -> bool:
    haystack = f"{url} {text}".lower()
    if url.lower().endswith((".pdf", ".xlsx", ".xls", ".csv")):
        return True
    return any(k in haystack for k in KEYWORDS)


def parse_candidate_links(html: str, base_url: str, registered_url: str) -> list[dict]:
    parser = _LinkParser()
    parser.feed(html or "")
    out: list[dict] = []
    seen: set[str] = set()
    for href, text in parser.links:
        absolute = urljoin(base_url, href)
        if absolute in seen:
            continue
        if not absolute.startswith("https://"):
            continue
        if not _host_allowed(absolute, registered_url):
            continue
        if not _is_candidate(absolute, text):
            continue
        seen.add(absolute)
        path = urlparse(absolute).path.lower()
        kind = "pdf" if path.endswith(".pdf") else ("spreadsheet" if path.endswith((".xlsx", ".xls", ".csv")) else "page")
        out.append({"url": absolute, "text": text[:300], "kind": kind})
    return out


async def discover_documents(symbol: str, timeout: float = 12.0) -> dict:
    symbol = str(symbol or "").upper().strip()
    source = get_source(symbol)
    if not source:
        return {"symbol": symbol, "ok": False, "error": "unmapped_symbol", "documents": []}

    start_url = str(source.get("primary_url") or "")
    if not start_url.startswith("https://"):
        return {"symbol": symbol, "ok": False, "error": "invalid_registered_url", "documents": []}

    headers = {
        "User-Agent": "CaracasBull-FundamentalAudit/1.0 (+official-source-discovery)",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = await client.get(start_url)
            response.raise_for_status()
    except Exception as exc:
        return {
            "symbol": symbol,
            "ok": False,
            "error": type(exc).__name__,
            "source_url": start_url,
            "documents": [],
        }

    final_url = str(response.url)
    if not _host_allowed(final_url, start_url):
        return {
            "symbol": symbol,
            "ok": False,
            "error": "redirect_outside_registered_host",
            "source_url": start_url,
            "final_url": final_url,
            "documents": [],
        }

    documents = parse_candidate_links(response.text, final_url, start_url)
    return {
        "symbol": symbol,
        "canonical_symbol": source.get("canonical_symbol"),
        "issuer": source.get("issuer"),
        "industry_type": source.get("industry_type"),
        "ok": True,
        "source_url": start_url,
        "final_url": final_url,
        "documents": documents,
        "count": len(documents),
    }
