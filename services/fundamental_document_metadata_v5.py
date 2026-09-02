"""Extracción fail-closed de metadatos documentales para fundamentales V5.

No decide cifras contables. Sólo intenta resolver, desde texto visible del PDF:
- fecha de corte del estado (as_of),
- período fiscal aproximable,
- moneda declarada,
- base monetaria (nominal / constante de cierre),
- indicios de auditoría.

Una pista sólo se marca `resolved=True` cuando la evidencia textual es explícita.
El nombre del archivo, la URL y la fecha de descarga NO se usan como sustituto.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO
import re
import unicodedata
from typing import Any, Iterable

from pypdf import PdfReader

_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
    "octubre": 10, "noviembre": 11, "diciembre": 12,
}

_DATE_RE = re.compile(
    r"(?<!\d)(?P<day>[0-3]?\d)\s+de\s+"
    r"(?P<month>enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
    r"(?:\s+de)?\s+(?P<year>20\d{2})(?!\d)",
    re.IGNORECASE,
)

_AUDIT_HINTS = (
    "informe de los contadores públicos independientes",
    "informe de los contadores publicos independientes",
    "informe del auditor independiente",
    "informe de auditoría independiente",
    "informe de auditoria independiente",
    "estados financieros auditados",
)

_CONSTANT_HINTS = (
    "bolívares constantes",
    "bolivares constantes",
    "moneda constante",
    "poder adquisitivo constante",
    "poder adquisitivo a la fecha",
    "reexpresados",
    "reexpresadas",
    "ajustados por inflación",
    "ajustados por inflacion",
)

_NOMINAL_HINTS = (
    "bolívares nominales",
    "bolivares nominales",
    "cifras nominales",
    "valores nominales",
)

_USD_HINTS = (
    "dólares estadounidenses",
    "dolares estadounidenses",
    "expresados en dólares",
    "expresados en dolares",
    "us$",
    "usd",
)

_VES_HINTS = (
    "expresados en bolívares",
    "expresados en bolivares",
    "bolívares",
    "bolivares",
    "bs.",
)


def _clean(text: str) -> str:
    raw = unicodedata.normalize("NFKC", str(text or ""))
    return " ".join(raw.replace("\u00a0", " ").split())


def _lower(text: str) -> str:
    return _clean(text).lower()


def _date_candidates(pages: Iterable[str], max_pages: int = 12) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page_no, raw in enumerate(pages or [], start=1):
        if page_no > max_pages:
            break
        text = _clean(raw)
        low = text.lower()
        for match in _DATE_RE.finditer(text):
            try:
                d = int(match.group("day"))
                m = _MONTHS[match.group("month").lower()]
                y = int(match.group("year"))
                iso = date(y, m, d).isoformat()
            except Exception:
                continue
            start = max(0, match.start() - 120)
            end = min(len(text), match.end() + 160)
            evidence = text[start:end]
            elow = evidence.lower()
            score = 0
            if any(k in elow for k in ("estado", "situación financiera", "situacion financiera", "resultado", "patrimonio", "flujo")):
                score += 5
            if any(k in elow for k in ("al ", "terminado", "finalizado", "por el año", "por el ano")):
                score += 3
            if page_no <= 8:
                score += 2
            if "nota" in elow and not any(k in elow for k in ("estado de", "estados financieros")):
                score -= 2
            out.append({"as_of": iso, "page": page_no, "evidence": evidence[:500], "score": score})
    return out


def infer_document_metadata_from_pages(pages: Iterable[str]) -> dict[str, Any]:
    page_list = [str(p or "") for p in (pages or [])]
    head_pages = page_list[:12]
    head_text = "\n".join(_clean(p) for p in head_pages)
    low = head_text.lower()

    dates = _date_candidates(head_pages)
    grouped: dict[str, dict[str, Any]] = {}
    for row in dates:
        key = row["as_of"]
        prev = grouped.get(key)
        if prev is None:
            grouped[key] = {**row, "mentions": 1}
        else:
            prev["mentions"] += 1
            if row["score"] > prev["score"]:
                prev.update({"page": row["page"], "evidence": row["evidence"], "score": row["score"]})
    ranked = sorted(grouped.values(), key=lambda r: (r["score"], r["mentions"], r["as_of"]), reverse=True)

    as_of = None
    as_of_meta: dict[str, Any] = {"resolved": False, "reason": "no_explicit_statement_date", "candidates": ranked[:6]}
    if ranked:
        best = ranked[0]
        tied = [r for r in ranked if r["score"] == best["score"] and r["mentions"] == best["mentions"]]
        # When several equally strong dates exist, prefer the latest only if they share the same page
        # and look like a standard comparative header. Otherwise remain unresolved.
        if len(tied) == 1:
            as_of = best["as_of"]
            as_of_meta = {"resolved": True, "method": "explicit_statement_date", **best, "candidates": ranked[:6]}
        else:
            same_page = len({r["page"] for r in tied}) == 1
            if same_page:
                chosen = max(tied, key=lambda r: r["as_of"])
                as_of = chosen["as_of"]
                as_of_meta = {"resolved": True, "method": "comparative_header_latest_explicit_date", **chosen, "candidates": ranked[:6]}
            else:
                as_of_meta = {"resolved": False, "reason": "ambiguous_explicit_statement_dates", "candidates": ranked[:6]}

    currency = None
    currency_evidence = None
    usd_hits = [h for h in _USD_HINTS if h in low]
    ves_hits = [h for h in _VES_HINTS if h in low]
    if usd_hits and not ves_hits:
        currency = "USD"
        currency_evidence = usd_hits[:4]
    elif ves_hits and not usd_hits:
        currency = "VES"
        currency_evidence = ves_hits[:4]
    elif usd_hits and ves_hits:
        # Mixed presentation is not auto-resolved; could be translations or note disclosures.
        currency_evidence = {"usd": usd_hits[:4], "ves": ves_hits[:4]}

    monetary_basis = None
    basis_evidence = None
    constant_hits = [h for h in _CONSTANT_HINTS if h in low]
    nominal_hits = [h for h in _NOMINAL_HINTS if h in low]
    if constant_hits and not nominal_hits:
        monetary_basis = "constant_ves_end_period"
        basis_evidence = constant_hits[:4]
    elif nominal_hits and not constant_hits:
        monetary_basis = "nominal_ves"
        basis_evidence = nominal_hits[:4]
    elif constant_hits and nominal_hits:
        basis_evidence = {"constant": constant_hits[:4], "nominal": nominal_hits[:4]}

    audit_hits = [h for h in _AUDIT_HINTS if h in low]
    audited = True if audit_hits else None

    fiscal_period = None
    if as_of:
        try:
            d = date.fromisoformat(as_of)
            fiscal_period = f"FY{d.year}" if d.month == 12 and d.day in {30, 31} else f"ASOF-{as_of}"
        except ValueError:
            pass

    required = {
        "as_of": bool(as_of),
        "currency": bool(currency),
        "monetary_basis": bool(monetary_basis) if currency == "VES" else bool(currency == "USD"),
        "audited": audited is True,
    }
    return {
        "resolved": all(required.values()),
        "as_of": as_of,
        "as_of_evidence": as_of_meta,
        "fiscal_period": fiscal_period,
        "currency": currency,
        "currency_evidence": currency_evidence,
        "monetary_basis": monetary_basis,
        "monetary_basis_evidence": basis_evidence,
        "audited": audited,
        "audit_evidence": audit_hits[:6],
        "required": required,
        "unresolved": sorted(k for k, ok in required.items() if not ok),
        "note": "published_at no se infiere del PDF; requiere publicación oficial separada.",
    }


def extract_document_metadata_from_pdf_bytes(data: bytes, max_pages: int = 12) -> dict[str, Any]:
    if not data or not bytes(data).startswith(b"%PDF"):
        return {"resolved": False, "error": "invalid_pdf", "unresolved": ["as_of", "currency", "monetary_basis", "audited"]}
    try:
        reader = PdfReader(BytesIO(data))
    except Exception as exc:
        return {"resolved": False, "error": f"pdf_parse_error:{type(exc).__name__}", "unresolved": ["as_of", "currency", "monetary_basis", "audited"]}
    pages = []
    for page in reader.pages[:max_pages]:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    meta = infer_document_metadata_from_pages(pages)
    meta["pages_scanned"] = len(pages)
    return meta
