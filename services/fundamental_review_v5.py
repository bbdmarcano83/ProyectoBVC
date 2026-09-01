"""Gate de revisión humana para candidatos fundamentales extraídos de PDF.

El parser produce múltiples candidatos con evidencia. Este módulo exige una
selección explícita por índice/campo, conserva la evidencia elegida y sólo luego
invoca el collector fail-closed (contabilidad + FX + persistencia).
"""
from __future__ import annotations

from typing import Any

from services.fundamental_collector_v5 import ingest_normalized_report, coverage_report
from services.fundamental_sources_v5 import get_source


def build_review_package(symbol: str, candidates: dict[str, list[dict]], *, source_url: str, as_of: str) -> dict:
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
            })
        if clean:
            fields[field] = clean
    return {
        "valid": bool(fields),
        "symbol": symbol,
        "canonical_symbol": source.get("canonical_symbol"),
        "industry_type": source.get("industry_type"),
        "source_url": source_url,
        "as_of": as_of,
        "fields": fields,
        "requires_explicit_selection": True,
        "note": "Ningún candidato se persiste hasta seleccionar explícitamente campo e índice.",
    }


def select_candidates(review: dict, selections: dict[str, int], *, extra_fields: dict[str, Any] | None = None) -> tuple[dict, dict]:
    if not review.get("valid"):
        return {}, {"valid": False, "reason": "invalid_review_package"}
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
        selected[field] = choice["value"]
        evidence[field] = {
            "page": choice.get("page"),
            "raw": choice.get("raw"),
            "alias": choice.get("alias"),
            "evidence": choice.get("evidence"),
        }
    return selected, {
        "valid": not errors and bool(selected),
        "errors": errors,
        "evidence": evidence,
        "selected_fields": sorted(selected),
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
) -> dict:
    """Acepta sólo una selección explícita y la pasa por todos los gates V5."""
    extras = dict(extra_fields or {})
    extras["currency"] = currency
    extras["monetary_basis"] = monetary_basis
    record, selected_meta = select_candidates(review, selections, extra_fields=extras)
    if not selected_meta.get("valid"):
        return {"accepted": False, "persisted": False, "selection": selected_meta}

    symbol = str(review.get("symbol") or "").upper()
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
    }
    return ingest_normalized_report(
        symbol,
        record,
        source_url=str(review.get("source_url") or ""),
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
