"""Diagnóstico read-only de RST FY2025 usando exclusivamente publicación BVC.

No persiste nada. Expone la evidencia OCR seleccionada, unidad y base monetaria
por campo para resolver discrepancias sin sustituir el documento certificado por
suposiciones o fuentes secundarias.
"""
from __future__ import annotations

import json

from scripts.fundamental_backfill_v5 import build_review
from services.fundamental_autoreview_v5 import propose_fail_closed_selections


def main() -> int:
    package = build_review("RST", "FY2025")
    review = package.get("review") or {}
    proposal = propose_fail_closed_selections(review)
    candidates = review.get("candidates") or {}

    selected = {}
    for field, index in (proposal.get("selections") or {}).items():
        rows = candidates.get(field) or []
        try:
            row = dict(rows[int(index)])
        except (IndexError, TypeError, ValueError):
            row = {"selection_error": True, "requested_index": index}
        selected[field] = row

    report = {
        "document": package.get("document"),
        "parse": package.get("parse"),
        "review_valid": review.get("valid"),
        "auto_review": proposal,
        "selected_evidence": selected,
        "detected_bases": sorted({
            str(row.get("page_monetary_basis"))
            for row in selected.values()
            if isinstance(row, dict) and row.get("page_monetary_basis")
        }),
        "detected_multipliers": sorted({
            float(row.get("page_value_multiplier"))
            for row in selected.values()
            if isinstance(row, dict) and row.get("page_value_multiplier") is not None
        }),
        "policy": "certified-data-first; source=BVC post 29952; no persistence",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
