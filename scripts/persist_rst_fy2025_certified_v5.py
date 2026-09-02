"""Backfill fail-closed de RST FY2025 desde evidencia certificada BVC.

La corrección de base monetaria sólo se permite porque todos los campos
seleccionados del estado certificado por BVC declaran consistentemente miles de
bolívares constantes. Si esa evidencia cambia, el script aborta antes de FX o DB.
"""
from __future__ import annotations

import json

from scripts.fundamental_backfill_v5 import build_review
from services.fundamental_autoreview_v5 import propose_fail_closed_selections
from services.fundamental_certifier_policy_v5 import certify_fundamental_source
from services.fundamental_review_v5 import accept_reviewed_snapshot

EXPECTED_BASIS = "constant_ves_end_period"
EXPECTED_MULTIPLIER = 1000.0


def _selected_rows(review: dict, selections: dict[str, int]) -> dict[str, dict]:
    fields = review.get("fields") or {}
    selected: dict[str, dict] = {}
    for field, raw_index in selections.items():
        idx = int(raw_index)
        choice = next((row for row in (fields.get(field) or []) if int(row.get("index", -1)) == idx), None)
        if not isinstance(choice, dict):
            raise RuntimeError(f"certified_selection_missing:{field}:{idx}")
        selected[field] = dict(choice)
    return selected


def persist() -> dict:
    package = build_review("RST", "FY2025")
    parse = package.get("parse") or {}
    review = package.get("review") or {}
    if not parse.get("valid") or not review.get("valid"):
        return {"accepted": False, "persisted": False, "error": "certified_bvc_parse_invalid", "parse": parse}

    certification = certify_fundamental_source("RST", str(parse.get("source_url") or ""))
    if not certification.get("valid") or certification.get("certifier") != "bvc":
        return {"accepted": False, "persisted": False, "error": "bvc_certification_required", "certification": certification}

    proposal = propose_fail_closed_selections(review)
    if not proposal.get("valid"):
        return {"accepted": False, "persisted": False, "error": "certified_autoreview_invalid", "auto_review": proposal}

    selected = _selected_rows(review, proposal.get("selections") or {})
    bases = {str(row.get("page_monetary_basis") or "") for row in selected.values()}
    multipliers = {float(row.get("page_value_multiplier")) for row in selected.values() if row.get("page_value_multiplier") is not None}
    if bases != {EXPECTED_BASIS}:
        return {"accepted": False, "persisted": False, "error": "certified_basis_not_uniform", "detected_bases": sorted(bases)}
    if multipliers != {EXPECTED_MULTIPLIER}:
        return {"accepted": False, "persisted": False, "error": "certified_multiplier_not_uniform", "detected_multipliers": sorted(multipliers)}

    assets = float(selected["total_assets"]["value"])
    liabilities = float(selected["total_liabilities"]["value"])
    equity = float(selected["equity"]["value"])
    equation_error = abs(assets - liabilities - equity)
    if equation_error > max(1.0, abs(assets) * 1e-9):
        return {
            "accepted": False,
            "persisted": False,
            "error": "certified_accounting_equation_mismatch",
            "accounting_error": equation_error,
        }

    result = accept_reviewed_snapshot(
        review,
        proposal.get("selections") or {},
        document_type="annual_audited_bvc_image_bundle",
        fiscal_period="FY2025",
        audited=True,
        currency="VES",
        monetary_basis=EXPECTED_BASIS,
        published_at=str(parse.get("published_at") or "") or None,
        value_multiplier=EXPECTED_MULTIPLIER,
        hydrate_fx=True,
        require_fx=True,
        document_metadata={
            "certified_basis_correction_v5": True,
            "certified_basis_source": "BVC post 29952",
            "certifier": "bvc",
            "certified_data_precedence": True,
            "selected_page_bases": sorted(bases),
            "selected_page_multipliers": sorted(multipliers),
        },
    )
    return {
        "certification": certification,
        "detected_bases": sorted(bases),
        "detected_multipliers": sorted(multipliers),
        "accounting_equation_error_reported_units": equation_error,
        "source_document_sha256": parse.get("source_document_sha256"),
        "published_at": parse.get("published_at"),
        "result": result,
    }


def main() -> int:
    report = persist()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    result = report.get("result") if isinstance(report.get("result"), dict) else report
    return 0 if result.get("accepted") else 1


if __name__ == "__main__":
    raise SystemExit(main())
