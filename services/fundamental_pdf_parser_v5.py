"""Extractor PDF V5 orientado a evidencia, no a auto-ingesta ciega.

Descarga documentos oficiales registrados y devuelve candidatos por campo con
página, columna comparativa y fragmento. No elige automáticamente entre múltiples
cifras ni guarda en Neon; la normalización/validación contable ocurre después.
Cada PDF descargado queda identificado por SHA-256 de sus bytes exactos.

La extracción prioriza filas contables reales. Esto evita que al aplanar una
página completa se mezclen notas, años y cifras de filas vecinas. El escaneo
amplio se conserva únicamente como fallback cuando un campo no aparece en filas.
También puede derivar total activo/pasivo exclusivamente como suma de sus filas
corriente + no corriente en la misma página y columna; esa derivación queda
marcada y conserva ambas evidencias.
"""
from __future__ import annotations

from io import BytesIO
import hashlib
import re
from urllib.parse import urlparse
from typing import Iterable

import httpx
from pypdf import PdfReader

from services.fundamental_sources_v5 import get_source

MAX_PDF_BYTES = 25 * 1024 * 1024

FIELD_ALIASES = {
    "total_assets": (
        "total del activo", "total activo", "total activos", "activos totales",
    ),
    "total_liabilities": (
        "total del pasivo", "total pasivo", "total pasivos", "pasivos totales",
    ),
    "equity": (
        "total patrimonio de los accionistas", "total patrimonio de accionistas",
        "total del patrimonio", "total patrimonio", "patrimonio total", "patrimonio",
    ),
    "net_income": (
        "utilidad (pérdida) neta", "utilidad (perdida) neta",
        "ganancia (pérdida) neta", "ganancia (perdida) neta",
        "resultado neto del año", "resultado neto del ejercicio",
        "resultado neto", "utilidad neta", "ganancia neta",
        "pérdida neta", "perdida neta",
    ),
    "revenue": ("ingresos totales", "ingresos", "ventas netas", "ventas"),
    "cash": ("efectivo y equivalentes", "disponibilidades", "efectivo"),
    "total_debt": ("deuda financiera", "deuda total", "obligaciones financieras"),
    "operating_cash_flow": ("flujo de efectivo de actividades operativas", "actividades operacionales"),
    "capex": ("adiciones de propiedad planta y equipo", "adiciones de propiedades planta y equipos", "inversiones de capital"),
    "nav": ("valor neto de los activos", "valor de unidad de inversión", "valor patrimonial"),
}

_COMPONENT_LABELS = {
    "assets_current": ("total activo corriente", "total activos corrientes"),
    "assets_noncurrent": (
        "total activo no corriente", "total activos no corrientes",
        "total activo no circulante", "total activos no circulantes",
    ),
    "liabilities_current": ("total pasivo corriente", "total pasivos corrientes"),
    "liabilities_noncurrent": (
        "total pasivo no corriente", "total pasivos no corrientes",
        "total pasivo no circulante", "total pasivos no circulantes",
        "total pasivos a largo plazo", "total pasivo a largo plazo",
    ),
}

# Deliberadamente NO acepta espacios como separador de miles. En PDFs comparativos
# un espacio normalmente separa columnas ("348.224.455 466.175.472"). Permitirlo
# convertía las dos columnas en un único número gigantesco. Espacios OCR del tipo
# "404. 499.712" se corrigen antes de aplicar la expresión regular.
_NUMBER_BODY = r"(?:\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[\.,]\d+)?)"
NUMBER_RE = re.compile(rf"(?<!\w)(?:Bs\.?\s*)?(?:\(-?{_NUMBER_BODY}\)|-?{_NUMBER_BODY})")
_YEAR_RE = re.compile(r"(?<!\d)(20\d{2})(?!\d)")

_ALL_ALIASES = tuple(sorted({a for aliases in FIELD_ALIASES.values() for a in aliases}, key=len, reverse=True))


def source_document_sha256(data: bytes) -> str | None:
    if not isinstance(data, (bytes, bytearray)) or not data:
        return None
    return hashlib.sha256(bytes(data)).hexdigest()


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
    for key in ("primary_url", "url", "source_url", "discovery_url"):
        value = src.get(key)
        if value:
            registered.append((urlparse(str(value)).hostname or "").lower())
    for value in src.get("urls", []) if isinstance(src.get("urls"), list) else []:
        registered.append((urlparse(str(value)).hostname or "").lower())
    registered = [h for h in registered if h]
    if not registered:
        return True
    return any(target == h or target.endswith("." + h) or h.endswith("." + target) for h in registered)


def _clean_row(raw: str) -> str:
    text = " ".join(str(raw or "").replace("\u00a0", " ").split())
    return re.sub(r"(?<=\.)\s+(?=\d{3}(?:\D|$))", "", text)


def _page_years(rows: list[str]) -> list[int]:
    """Return ordered distinct years visible near the statement header.

    We intentionally inspect only the first part of the page so dates embedded in
    notes do not decide comparative-column order.
    """
    found: list[int] = []
    for row in rows[:24]:
        for raw in _YEAR_RE.findall(row):
            year = int(raw)
            if year not in found:
                found.append(year)
    return found[:3]


def _after_alias_until_next_label(text: str, alias: str, idx: int) -> str:
    start = idx + len(alias)
    end = len(text)
    lower = text.lower()
    for other in _ALL_ALIASES:
        pos = lower.find(other, start)
        if pos >= 0 and pos < end:
            end = pos
    return text[start:end]


def _append_matches(
    bucket: list[dict], *, page_no: int, alias: str, occurrence: int,
    evidence: str, scan_text: str, context_quality: str,
    page_years: list[int] | None = None,
) -> int:
    added = 0
    matches = NUMBER_RE.findall(scan_text)
    for column_index, token in enumerate(matches[:3]):
        value = _normalize_number(token)
        if value is None:
            continue
        bucket.append({
            "value": value,
            "raw": token,
            "page": page_no,
            "alias": alias,
            "evidence": evidence,
            "column_index": column_index,
            "occurrence": occurrence,
            "context_quality": context_quality,
            "page_years": list(page_years or []),
        })
        added += 1
    return added


def _component_rows(rows: list[str], page_no: int, years: list[int]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {key: [] for key in _COMPONENT_LABELS}
    for row in rows:
        lower = row.lower()
        for key, labels in _COMPONENT_LABELS.items():
            matched = next((label for label in labels if label in lower), None)
            if not matched:
                continue
            idx = lower.find(matched)
            scan = row[idx + len(matched):]
            for col, token in enumerate(NUMBER_RE.findall(scan)[:3]):
                value = _normalize_number(token)
                if value is None:
                    continue
                out[key].append({
                    "value": value, "raw": token, "page": page_no,
                    "column_index": col, "evidence": row[:500],
                    "page_years": list(years),
                })
    return out


def _derive_total_candidates(candidates: dict[str, list[dict]], components: dict[str, list[dict]], page_no: int) -> None:
    pairs = (
        ("total_assets", "assets_current", "assets_noncurrent"),
        ("total_liabilities", "liabilities_current", "liabilities_noncurrent"),
    )
    for target, left_key, right_key in pairs:
        left = components.get(left_key) or []
        right = components.get(right_key) or []
        for a in left:
            for b in right:
                if a.get("column_index") != b.get("column_index"):
                    continue
                value = float(a["value"]) + float(b["value"])
                # Avoid duplicating an already extracted exact total with same page/column/value.
                duplicate = any(
                    x.get("page") == page_no
                    and x.get("column_index") == a.get("column_index")
                    and abs(float(x.get("value") or 0.0) - value) <= max(1.0, abs(value)) * 1e-9
                    for x in candidates[target]
                )
                if duplicate:
                    continue
                candidates[target].append({
                    "value": value,
                    "raw": f"{a.get('raw')} + {b.get('raw')}",
                    "page": page_no,
                    "alias": f"derived_{target}",
                    "evidence": f"{a.get('evidence')} | {b.get('evidence')}",
                    "column_index": a.get("column_index"),
                    "occurrence": -1,
                    "context_quality": "derived_accounting_total",
                    "page_years": list(a.get("page_years") or b.get("page_years") or []),
                    "derived_from": [left_key, right_key],
                })


def extract_candidates_from_pages(pages: Iterable[str]) -> dict:
    candidates: dict[str, list[dict]] = {field: [] for field in FIELD_ALIASES}
    for page_no, raw_text in enumerate(pages or [], start=1):
        raw_page = str(raw_text or "")
        rows = [_clean_row(line) for line in raw_page.splitlines() if _clean_row(line)]
        years = _page_years(rows)
        row_hits: dict[str, int] = {field: 0 for field in FIELD_ALIASES}

        for field, aliases in FIELD_ALIASES.items():
            occurrence = 0
            for row in rows:
                lower = row.lower()
                for alias in aliases:
                    start = 0
                    while True:
                        idx = lower.find(alias, start)
                        if idx < 0:
                            break
                        scan = _after_alias_until_next_label(row, alias, idx)
                        added = _append_matches(
                            candidates[field], page_no=page_no, alias=alias,
                            occurrence=occurrence, evidence=row[:500], scan_text=scan,
                            context_quality="accounting_row", page_years=years,
                        )
                        row_hits[field] += added
                        occurrence += 1
                        start = idx + len(alias)

        components = _component_rows(rows, page_no, years)
        _derive_total_candidates(candidates, components, page_no)

        flat = _clean_row(raw_page)
        lower_flat = flat.lower()
        for field, aliases in FIELD_ALIASES.items():
            if row_hits[field] > 0:
                continue
            occurrence = 0
            for alias in aliases:
                start = 0
                while True:
                    idx = lower_flat.find(alias, start)
                    if idx < 0:
                        break
                    window = flat[max(0, idx - 80): min(len(flat), idx + len(alias) + 180)]
                    after = flat[idx + len(alias): min(len(flat), idx + len(alias) + 140)]
                    _append_matches(
                        candidates[field], page_no=page_no, alias=alias,
                        occurrence=occurrence, evidence=window, scan_text=after,
                        context_quality="page_fallback", page_years=years,
                    )
                    occurrence += 1
                    start = idx + len(alias)

    return {k: v for k, v in candidates.items() if v}


def parse_pdf_bytes(data: bytes) -> tuple[dict, dict]:
    if not data or len(data) > MAX_PDF_BYTES:
        return {}, {"valid": False, "reason": "pdf_empty_or_too_large"}
    digest = source_document_sha256(data)
    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:
        return {}, {"valid": False, "reason": f"pdf_parse_error:{type(exc).__name__}", "source_document_sha256": digest}
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
    row_candidates = sum(1 for options in candidates.values() for option in options if option.get("context_quality") == "accounting_row")
    derived_candidates = sum(1 for options in candidates.values() for option in options if option.get("context_quality") == "derived_accounting_total")
    return candidates, {
        "valid": bool(candidates), "pages": len(pages), "empty_pages": empty_pages,
        "fields_with_candidates": len(candidates), "accounting_row_candidates": row_candidates,
        "derived_accounting_candidates": derived_candidates, "requires_review": True,
        "source_document_sha256": digest,
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
    digest = source_document_sha256(data)
    if not data.startswith(b"%PDF"):
        return {}, {
            "valid": False, "reason": "download_not_pdf", "symbol": symbol,
            "source_url": url, "bytes": len(data), "content_type": content_type,
            "source_document_sha256": digest,
        }
    candidates, meta = parse_pdf_bytes(data)
    meta.update({
        "symbol": symbol, "source_url": url, "bytes": len(data),
        "content_type": content_type, "source_document_sha256": digest,
    })
    return candidates, meta
