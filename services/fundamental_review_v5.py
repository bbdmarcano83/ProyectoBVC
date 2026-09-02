"""Gate de revisión humana para candidatos fundamentales extraídos de PDF.

El parser produce múltiples candidatos con evidencia. Este módulo exige una
selección explícita por índice/campo, conserva la evidencia elegida y sólo luego
invoca el collector fail-closed (contabilidad + FX + persistencia). Cuando el
parser dispone del SHA-256 del PDF, la huella se conserva en metadata auditable.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
from math import isfinite

from services.fundamental_certifier_policy_v5 import certify_fundamental_source
from services.fundamental_collector_v5 import ingest_normalized_report, coverage_report
from services.fundamental_sources_v5 import get_source


def _infer_preferred_column(fields: dict[str, list[dict]]) -> tuple[int | None, dict]:
    """Infer the latest comparative column from the primary accounting page.

    Notes later in a report may reverse year order, so global voting is unsafe.
    We instead choose the earliest page containing explicit accounting rows for
    at least two core statement fields, and accept its year order only when the
    two leading years are adjacent and all usable rows on that page agree.
    """
    by_page: dict[int, list[dict]] = defaultdict(list)
    core_fields = ("total_assets", "total_liabilities", "equity", "net_income", "revenue")
    for field in core_fields:
        for option in fields.get(field) or []:
            if option.get("context_quality") not in {"accounting_row", "derived_accounting_total"}:
                continue
            try:
                page = int(option.get("page"))
            except (TypeError, ValueError):
                continue
            years = [int(y) for y in (option.get("page_years") or []) if str(y).isdigit()]
            if len(years) < 2 or years[0] == years[1] or abs(years[0] - years[1]) != 1:
                continue
            preferred = 0 if years[0] > years[1] else 1
            by_page[page].append({"field": field, "page": page, "years": years[:2], "preferred": preferred})

    diagnostics = []
    for page in sorted(by_page):
        evidence = by_page[page]
        distinct_fields = sorted({row["field"] for row in evidence})
        counts = Counter(row["preferred"] for row in evidence)
        diagnostics.append({"page": page, "fields": distinct_fields, "votes": dict(counts)})
        if len(distinct_fields) < 2:
            continue
        winner, winner_count = counts.most_common(1)[0]
        total = sum(counts.values())
        if winner_count < 2 or winner_count / max(1, total) < 0.90:
            continue
        return winner, {
            "valid": True,
            "method": "primary_accounting_page_ordered_adjacent_year_headers",
            "preferred_column": winner,
            "primary_page": page,
            "votes": dict(counts),
            "fields": distinct_fields,
            "evidence": evidence[:12],
        }

    return None, {
        "valid": False,
        "reason": "no_coherent_primary_accounting_period_header",
        "pages_considered": diagnostics[:12],
    }


def build_review_package(
    symbol: str,
    candidates: dict[str, list[dict]],
    *,
    source_url: str,
    as_of: str,
    source_document_sha256: str | None = None,
) -> dict:
    symbol = str(symbol or "").upper().strip()
    source = get_source(symbol)
    if not source:
        return {"valid": False, "reason": "unregistered_symbol", "symbol": symbol}
    fields = {}
    for field, options in (candidates or {}).items():
        clean = []
        for idx, option in enumerate(options or []):
            if not isinstance(option, dict) or option.get("value") is None:
                continue
            clean.append({
                "index": idx,
                "value": option.get("value"),
                "raw": option.get("raw"),
                "page": option.get("page"),
                "alias": option.get("alias"),
                "evidence": option.get("evidence"),
                "column_index": option.get("column_index"),
                "occurrence": option.get("occurrence"),
                "context_quality": option.get("context_quality"),
                "page_years": option.get("page_years") or [],
                "derived_from": option.get("derived_from") or [],
                "page_value_multiplier": option.get("page_value_multiplier"),
                "page_statement_unit": option.get("page_statement_unit"),
                "page_monetary_basis": option.get("page_monetary_basis"),
            })
        if clean:
            fields[field] = clean
    digest = str(source_document_sha256 or "").lower().strip()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        digest = ""
    preferred_column, preferred_meta = _infer_preferred_column(fields)
    return {
        "valid": bool(fields),
        "symbol": symbol,
        "canonical_symbol": source.get("canonical_symbol"),
        "industry_type": source.get("industry_type"),
        "source_url": source_url,
        "source_document_sha256": digest or None,
        "as_of": as_of,
        "fields": fields,
        "preferred_column": preferred_column,
        "preferred_column_evidence": preferred_meta,
        "requires_explicit_selection": True,
        "note": "Ningún candidato se persiste hasta seleccionar explícitamente campo e índice.",
    }


def select_candidates(
    review: dict,
    selections: dict[str, int],
    *,
    extra_fields: dict[str, Any] | None = None,
    value_multiplier: float = 1.0,
) -> tuple[dict, dict]:
    if not review.get("valid"):
        return {}, {"valid": False, "reason": "invalid_review_package"}
    try:
        multiplier = float(value_multiplier)
    except (TypeError, ValueError):
        multiplier = 0.0
    if not isfinite(multiplier) or multiplier <= 0:
        return {}, {"valid": False, "reason": "invalid_value_multiplier", "errors": ["value_multiplier:invalido"]}
    selected: dict[str, Any] = dict(extra_fields or {})
    evidence: dict[str, dict] = {}
    errors = []
    fields = review.get("fields") or {}
    for field, index in (selections or {}).items():
        options = fields.get(field)
        if not options:
            errors.append(f"{field}:sin_candidatos")
            continue
        try:
            idx = int(index)
        except (TypeError, ValueError):
            errors.append(f"{field}:indice_invalido")
            continue
        choice = next((o for o in options if int(o.get("index", -1)) == idx), None)
        if choice is None:
            errors.append(f"{field}:indice_fuera_de_rango")
            continue
        detected_multiplier = choice.get("page_value_multiplier")
        if detected_multiplier is not None and abs(float(detected_multiplier) - multiplier) > 1e-9:
            errors.append(f"{field}:escala_declarada_no_coincide_con_folio")
            continue
        selected[field] = float(choice["value"]) * multiplier
        evidence[field] = {
            "page": choice.get("page"),
            "raw": choice.get("raw"),
            "alias": choice.get("alias"),
            "evidence": choice.get("evidence"),
            "column_index": choice.get("column_index"),
            "occurrence": choice.get("occurrence"),
            "context_quality": choice.get("context_quality"),
            "page_years": choice.get("page_years") or [],
            "derived_from": choice.get("derived_from") or [],
            "reported_value_multiplier": multiplier,
            "normalized_value": selected[field],
            "page_statement_unit": choice.get("page_statement_unit"),
            "page_monetary_basis": choice.get("page_monetary_basis"),
        }
    return selected, {
        "valid": not errors and bool(selected),
        "errors": errors,
        "evidence": evidence,
        "selected_fields": sorted(selected),
        "reported_value_multiplier": multiplier,
    }


def accept_reviewed_snapshot(
    review: dict,
    selections: dict[str, int],
    *,
    document_type: str,
    fiscal_period: str,
    audited: bool,
    currency: str,
    monetary_basis: str,
    period_start: str | None = None,
    published_at: str | None = None,
    extra_fields: dict[str, Any] | None = None,
    hydrate_fx: bool = True,
    require_fx: bool = True,
    value_multiplier: float = 1.0,
    document_metadata: dict[str, Any] | None = None,
) -> dict:
    """Acepta sólo una selección explícita y la pasa por todos los gates V5.

    La base monetaria detectada de forma uniforme en un documento certificado
    prevalece sobre metadata declarativa del manifiesto. Si la evidencia
    certificada se contradice entre folios/campos, el proceso falla cerrado.
    """
    extras = dict(extra_fields or {})
    extras["currency"] = currency
    extras["monetary_basis"] = monetary_basis
    record, selected_meta = select_candidates(
        review,
        selections,
        extra_fields=extras,
        value_multiplier=value_multiplier,
    )
    if not selected_meta.get("valid"):
        return {"accepted": False, "persisted": False, "selection": selected_meta}

    symbol = str(review.get("symbol") or "").upper()
    source_url = str(review.get("source_url") or "")
    detected_bases = {
        str(row.get("page_monetary_basis"))
        for row in (selected_meta.get("evidence") or {}).values()
        if row.get("page_monetary_basis")
    }
    certified_basis_override = None
    if len(detected_bases) > 1:
        return {
            "accepted": False,
            "persisted": False,
            "selection": selected_meta,
            "error": "certified_monetary_basis_conflict",
            "detected_monetary_basis": sorted(detected_bases),
        }
    if len(detected_bases) == 1:
        detected_basis = next(iter(detected_bases))
        if monetary_basis != detected_basis:
            certification = certify_fundamental_source(symbol, source_url)
            if not certification.get("valid"):
                return {
                    "accepted": False,
                    "persisted": False,
                    "selection": selected_meta,
                    "error": "declared_monetary_basis_mismatch",
                    "detected_monetary_basis": sorted(detected_bases),
                    "certification": certification,
                }
            certified_basis_override = {
                "declared_monetary_basis": monetary_basis,
                "certified_monetary_basis": detected_basis,
                "certifier": certification.get("certifier"),
                "policy": "certified_document_evidence_precedes_manifest_metadata",
            }
            record["monetary_basis"] = detected_basis

    coverage = coverage_report(symbol, record)
    if coverage.get("coverage_pct", 0) < 66.0:
        return {
            "accepted": False,
            "persisted": False,
            "selection": selected_meta,
            "coverage": coverage,
            "error": "reviewed_coverage_insufficient",
        }

    metadata = {
        "review_gate": "explicit_candidate_selection",
        "selected_evidence": selected_meta.get("evidence", {}),
        "review_required": False,
        "preferred_column_evidence": review.get("preferred_column_evidence"),
        "reported_value_multiplier": selected_meta.get("reported_value_multiplier", 1.0),
    }
    if certified_basis_override:
        metadata["certified_basis_override_v5"] = certified_basis_override
    if isinstance(document_metadata, dict):
        metadata.update({
            str(key): value for key, value in document_metadata.items()
            if value is not None
        })
    digest = str(review.get("source_document_sha256") or "").strip().lower()
    if len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest):
        metadata["source_document_sha256"] = digest

    return ingest_normalized_report(
        symbol,
        record,
        source_url=source_url,
        as_of=str(review.get("as_of") or ""),
        document_type=document_type,
        fiscal_period=fiscal_period,
        audited=audited,
        published_at=published_at,
        metadata=metadata,
        period_start=period_start,
        hydrate_fx=hydrate_fx,
        require_fx=require_fx,
    )
