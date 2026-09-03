"""Bounded discovery for curated tier-B fundamental sources.

This module is deliberately separate from official-source discovery. It never
widens the issuer/BVC/SUNAVAL allowlist. A URL is traversed only when the exact
symbol/host is present in ``SECONDARY_SOURCE_REGISTRY`` and the central evidence
classifier confirms ``B_SECONDARY``. Redirects and discovered links are checked
again before they are returned.
"""
from __future__ import annotations

from collections import deque
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urldefrag

import httpx

from services.fundamental_certifier_policy_v5 import classify_fundamental_source
from services.fundamental_secondary_sources_v5 import secondary_start_urls, secondary_source_for_url

KEYWORDS = (
    "estado", "financ", "audit", "informe", "gestion", "gestión", "balance",
    "resultado", "memoria", "report", "financial", "annual", "prospecto",
    "accionista", "asamblea", "2022", "2023", "2024", "2025", "2026",
)


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._href = str(href)
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(str(data))

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = None
            self._text = []


def _tier_b(symbol: str, url: str) -> dict | None:
    evidence = classify_fundamental_source(symbol, url)
    if evidence.get("admissible") and evidence.get("evidence_tier") == "B_SECONDARY":
        return evidence
    return None


def _same_curated_source(symbol: str, root_url: str, candidate_url: str) -> bool:
    root = secondary_source_for_url(symbol, root_url)
    candidate = secondary_source_for_url(symbol, candidate_url)
    if not root or not candidate:
        return False
    rhost = (urlparse(root_url).hostname or "").lower().removeprefix("www.")
    chost = (urlparse(candidate_url).hostname or "").lower().removeprefix("www.")
    if rhost != chost:
        return False
    return bool(_tier_b(symbol, candidate_url))


def _candidate(url: str, text: str) -> bool:
    path = urlparse(url).path.lower()
    if path.endswith((".pdf", ".xlsx", ".xls", ".csv")):
        return True
    haystack = f"{url} {text}".lower()
    return any(k in haystack for k in KEYWORDS)


def _crawlable(url: str, text: str) -> bool:
    path = urlparse(url).path.lower()
    if path.endswith((".pdf", ".xlsx", ".xls", ".csv", ".jpg", ".jpeg", ".png", ".zip")):
        return False
    haystack = f"{path} {text}".lower()
    return any(k in haystack for k in KEYWORDS)


async def discover_secondary_documents(
    symbol: str,
    timeout: float = 12.0,
    *,
    max_pages_per_source: int = 6,
    max_depth: int = 1,
) -> dict:
    """Return candidates only from explicitly curated tier-B routes."""
    symbol = str(symbol or "").upper().strip()
    starts = secondary_start_urls(symbol)
    if not starts:
        return {"symbol": symbol, "ok": True, "documents": [], "count": 0, "sources": 0, "errors": []}

    headers = {
        "User-Agent": "CaracasBull-FundamentalAudit/1.0 (+curated-secondary-discovery)",
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.5",
    }
    documents: list[dict] = []
    seen_docs: set[str] = set()
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for start in starts:
            root_url = str(start.get("url") or "").strip()
            if not _tier_b(symbol, root_url):
                errors.append(f"start_not_tier_b:{root_url}")
                continue

            if urlparse(root_url).path.lower().endswith(".pdf"):
                if root_url not in seen_docs:
                    documents.append({
                        "url": root_url,
                        "text": start.get("source_name") or "curated secondary PDF",
                        "kind": "pdf",
                        "discovery_depth": 0,
                        "source_name": start.get("source_name"),
                        "route": start.get("route"),
                        "confidence": int(start.get("confidence") or 0),
                    })
                    seen_docs.add(root_url)
                continue

            queue = deque([(root_url, 0)])
            visited: set[str] = set()
            while queue and len(visited) < max_pages_per_source:
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
                final_url = str(response.url)
                if not _same_curated_source(symbol, root_url, final_url):
                    errors.append(f"redirect_outside_curated_source:{page_url}")
                    continue
                ctype = str(response.headers.get("content-type") or "").lower()
                if response.content.startswith(b"%PDF") or "application/pdf" in ctype:
                    if final_url not in seen_docs:
                        documents.append({
                            "url": final_url,
                            "text": start.get("source_name") or "curated secondary PDF",
                            "kind": "pdf",
                            "discovery_depth": depth,
                            "source_name": start.get("source_name"),
                            "route": start.get("route"),
                            "confidence": int(start.get("confidence") or 0),
                        })
                        seen_docs.add(final_url)
                    continue

                parser = _Links()
                try:
                    parser.feed(response.text or "")
                except Exception:
                    continue
                for href, text in parser.links:
                    absolute = urldefrag(urljoin(final_url, href))[0]
                    if not absolute.startswith("https://"):
                        continue
                    if not _same_curated_source(symbol, root_url, absolute):
                        continue
                    path = urlparse(absolute).path.lower()
                    kind = "pdf" if path.endswith(".pdf") else ("spreadsheet" if path.endswith((".xlsx", ".xls", ".csv")) else "page")
                    if _candidate(absolute, text) and absolute not in seen_docs:
                        documents.append({
                            "url": absolute,
                            "text": text[:300],
                            "kind": kind,
                            "discovery_depth": depth,
                            "source_name": start.get("source_name"),
                            "route": start.get("route"),
                            "confidence": int(start.get("confidence") or 0),
                        })
                        seen_docs.add(absolute)
                    if depth < max_depth and absolute not in visited and _crawlable(absolute, text):
                        queue.append((absolute, depth + 1))

    return {
        "symbol": symbol,
        "ok": True,
        "documents": documents,
        "count": len(documents),
        "sources": len(starts),
        "errors": errors[:12],
    }
