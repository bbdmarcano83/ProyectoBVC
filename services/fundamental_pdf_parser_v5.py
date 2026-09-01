"""Extractor PDF V5 orientado a evidencia, no a auto-ingesta ciega.

Descarga documentos oficiales registrados y devuelve candidatos por campo con
página, columna comparativa y fragmento. No elige automáticamente entre múltiples
cifras ni guarda en Neon; la normalización/validación contable ocurre después.
"""
from __future__ import annotations

from io import BytesIO
import re
from urllib.parse import urlparse
from typing import Iterable

import httpx
from pypdf import PdfReader

from services.fundamental_sources_v5 import get_source

MAX_PDF_BYTES = 25 * 1024 * 1024

FIELD_ALIASES = {
    "total_assets": ("total activo", "total activos", "activos totales"),
    "total_liabilities": ("total pasivo", "total pasivos", "pasivos totales"),
    "equity": ("total patrimonio", "patrimonio total", "patrimonio"),
    "net_income": ("resultado neto", "utilidad neta", "ganancia neta", "pérdida neta", "perdida neta"),
    "revenue": ("ingresos totales", "ingresos", "ventas netas", "ventas"),
    "cash": ("efectivo y equivalentes", "disponibilidades", "efectivo"),
    "total_debt": ("deuda financiera", "deuda total", "obligaciones financieras"),
    "operating_cash_flow": ("flujo de efectivo de actividades operativas", "actividades operacionales"),
    "capex": ("adiciones de propiedad planta y equipo", "adiciones de propiedades planta y equipos", "inversiones de capital"),
    "nav": ("valor neto de los activos", "valor de unidad de inversión", "valor patrimonial"),
}

_NUMBER_BODY = r"(?:\d{1,3}(?:[\.\s]\d{3})*(?:,\d+)?|\d+(?:[\.,]\d+)?)"
NUMBER_RE = re.compile(rf"(?<!\w)(?:Bs\.?\s*)?(?:\(-?{_NUMBER_BODY}\)|-?{_NUMBER_BODY})")


def _normalize_number(raw: str) -> float | None:
    s = str(raw or "").strip().lower().replace("bs.", "").replace("bs", "").replace(" ", "")
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if not s:
        return None
    try:
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif s.count(".") > 1:
            s = s.replace(".", "")
        value = float(s)
        return -abs(value) if negative else value
    except ValueError:
        return None


def _official_host_allowed(symbol: str, url: str) -> bool:
    src = get_source(symbol)
    if not src:
        return False
    target = (urlparse(url).hostname or "").lower()
    if not target:
        return False
    registered = []
    for key in ("url", "source_url", "discovery_url"):
        value = src.get(key)
        if value:
            registered.append((urlparse(str(value)).hostname or "").lower())
    for value in src.get("urls", []) if isinstance(src.get("urls"), list) else []:
        registered.append((urlparse(str(value)).hostname or "").lower())
    registered = [h for h in registered if h]
    if not registered:
        return True
    return any(target == h or target.endswith("." + h) or h.endswith("." + target) for h in registered)


def extract_candidates_from_pages(pages: Iterable[str]) -> dict:
    candidates: dict[str, list[dict]] = {field: [] for field in FIELD_ALIASES}
    for page_no, raw_text in enumerate(pages or [], start=1):
        text = " ".join(str(raw_text or "").split())
        lower = text.lower()
        for field, aliases in FIELD_ALIASES.items():
            for alias in aliases:
                start = 0
                occurrence = 0
                while True:
                    idx = lower.find(alias, start)
                    if idx < 0:
                        break
                    window = text[max(0, idx - 80): min(len(text), idx + len(alias) + 180)]
                    after = text[idx + len(alias): min(len(text), idx + len(alias) + 140)]
                    matches = NUMBER_RE.findall(after)
                    for column_index, token in enumerate(matches[:3]):
                        value = _normalize_number(token)
                        if value is None:
                            continue
                        candidates[field].append({
                            "value": value,
                            "raw": token,
                            "page": page_no,
                            "alias": alias,
                            "evidence": window,
                            "column_index": column_index,
                            "occurrence": occurrence,
                        })
                    occurrence += 1
                    start = idx + len(alias)
    return {k: v for k, v in candidates.items() if v}


def parse_pdf_bytes(data: bytes) -> tuple[dict, dict]:
    if not data or len(data) > MAX_PDF_BYTES:
        return {}, {"valid": False, "reason": "pdf_empty_or_too_large"}
    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:
        return {}, {"valid": False, "reason": f"pdf_parse_error:{type(exc).__name__}"}
    pages = []
    empty_pages = 0
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if not text.strip():
            empty_pages += 1
        pages.append(text)
    candidates = extract_candidates_from_pages(pages)
    return candidates, {
        "valid": bool(candidates),
        "pages": len(pages),
        "empty_pages": empty_pages,
        "fields_with_candidates": len(candidates),
        "requires_review": True,
    }


def fetch_and_parse_official_pdf(symbol: str, url: str, timeout: float = 20.0) -> tuple[dict, dict]:
    symbol = str(symbol or "").upper().strip()
    if not url.startswith("https://"):
        return {}, {"valid": False, "reason": "https_required"}
    if not get_source(symbol):
        return {}, {"valid": False, "reason": "unregistered_symbol"}
    if not _official_host_allowed(symbol, url):
        return {}, {"valid": False, "reason": "host_not_registered_for_issuer"}
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; CaracasBull-FundamentalAudit/1.0)",
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.5",
        }
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
            data = response.content
            content_type = str(response.headers.get("content-type") or "").lower()
    except Exception as exc:
        return {}, {"valid": False, "reason": f"download_error:{type(exc).__name__}"}
    if not data.startswith(b"%PDF"):
        return {}, {
            "valid": False,
            "reason": "download_not_pdf",
            "symbol": symbol,
            "source_url": url,
            "bytes": len(data),
            "content_type": content_type,
        }
    candidates, meta = parse_pdf_bytes(data)
    meta.update({"symbol": symbol, "source_url": url, "bytes": len(data), "content_type": content_type})
    return candidates, meta
