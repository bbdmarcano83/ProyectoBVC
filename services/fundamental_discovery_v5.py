"""Descubrimiento seguro de documentos fundamentales V5.

Sólo navega el host oficial registrado para el símbolo. Puede seguir un número
muy limitado de subpáginas con semántica financiera (reportes, balances,
asambleas, etc.) y devuelve enlaces candidatos del mismo host. No extrae cifras
ni persiste nada.
"""
from __future__ import annotations

from collections import deque
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urldefrag

import httpx

from services.fundamental_sources_v5 import get_source

KEYWORDS = (
    "estado", "financ", "audit", "informe", "gestion", "gestión", "trimes",
    "semes", "anual", "balance", "accionista", "inversionista", "prospecto",
    "resultado", "memoria", "report", "financial", "annual", "quarter",
    "asamblea", "documento",
)

_CRAWL_HINTS = (
    "estado", "financ", "audit", "informe", "balance", "report", "asamblea",
    "accionista", "inversionista", "document", "annual", "quarter", "fondo",
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


def _is_crawl_page(url: str, text: str) -> bool:
    path = urlparse(url).path.lower()
    if path.endswith((".pdf", ".xlsx", ".xls", ".csv", ".jpg", ".jpeg", ".png", ".zip")):
        return False
    haystack = f"{path} {text}".lower()
    if any(k in haystack for k in _CRAWL_HINTS):
        return True
    # Year-index pages underneath already-financial routes (e.g. /reportes/.../2026).
    segments = [p for p in path.split("/") if p]
    return any(seg.isdigit() and len(seg) == 4 and 2020 <= int(seg) <= 2035 for seg in segments)


def _parsed_links(html: str, base_url: str, registered_url: str) -> list[tuple[str, str]]:
    parser = _LinkParser()
    parser.feed(html or "")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href, text in parser.links:
        absolute = urldefrag(urljoin(base_url, href))[0]
        if absolute in seen or not absolute.startswith("https://"):
            continue
        if not _host_allowed(absolute, registered_url):
            continue
        seen.add(absolute)
        out.append((absolute, text[:300]))
    return out


def parse_candidate_links(html: str, base_url: str, registered_url: str) -> list[dict]:
    out: list[dict] = []
    for absolute, text in _parsed_links(html, base_url, registered_url):
        if not _is_candidate(absolute, text):
            continue
        path = urlparse(absolute).path.lower()
        kind = "pdf" if path.endswith(".pdf") else ("spreadsheet" if path.endswith((".xlsx", ".xls", ".csv")) else "page")
        out.append({"url": absolute, "text": text, "kind": kind})
    return out


async def discover_documents(symbol: str, timeout: float = 12.0, *, max_pages: int = 8, max_depth: int = 2) -> dict:
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
    documents: list[dict] = []
    doc_seen: set[str] = set()
    visited: set[str] = set()
    queue = deque([(start_url, 0)])
    final_url = start_url
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        while queue and len(visited) < max_pages:
            page_url, depth = queue.popleft()
            if page_url in visited:
                continue
            visited.add(page_url)
            try:
                response = await client.get(page_url)
                response.raise_for_status()
            except Exception as exc:
                errors.append(f"{type(exc).__name__}:{page_url}")
                continue
            resolved = str(response.url)
            if not _host_allowed(resolved, start_url):
                errors.append(f"redirect_outside_registered_host:{page_url}")
                continue
            if depth == 0:
                final_url = resolved
            links = _parsed_links(response.text, resolved, start_url)
            for absolute, text in links:
                if _is_candidate(absolute, text) and absolute not in doc_seen:
                    path = urlparse(absolute).path.lower()
                    kind = "pdf" if path.endswith(".pdf") else ("spreadsheet" if path.endswith((".xlsx", ".xls", ".csv")) else "page")
                    documents.append({"url": absolute, "text": text, "kind": kind, "discovery_depth": depth})
                    doc_seen.add(absolute)
                if depth < max_depth and absolute not in visited and _is_crawl_page(absolute, text):
                    queue.append((absolute, depth + 1))

    if not visited or (len(visited) == 1 and errors and not documents):
        return {
            "symbol": symbol, "ok": False, "error": errors[0].split(":", 1)[0] if errors else "discovery_failed",
            "source_url": start_url, "documents": [], "visited_pages": len(visited),
        }

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
        "visited_pages": len(visited),
        "discovery_errors": errors[:5],
    }
