"""Diagnóstico read-only de candidatos de resultado neto en documentos certificados.

No persiste nada. Expone únicamente la evidencia necesaria para resolver la fila
de net_income de períodos que ya tienen documento oficial del emisor/BVC/SUNAVAL.
"""
from __future__ import annotations

import json

from scripts.fundamental_backfill_v5 import build_review
from services.fundamental_certifier_policy_v5 import certify_fundamental_source

TARGETS = (
    ("ABC.A", "FY2022"),
    ("BPV", "FY2022"),
    ("BPV", "FY2023"),
    ("BPV", "FY2024"),
    ("BPV", "FY2025"),
    ("IVC.A", "FY2024"),
    ("IVC.A", "FY2025"),
)


def _compact_option(option: dict) -> dict:
    return {
        "index": option.get("index"),
        "value": option.get("value"),
        "raw": option.get("raw"),
        "page": option.get("page"),
        "alias": option.get("alias"),
        "evidence": option.get("evidence"),
        "column_index": option.get("column_index"),
        "context_quality": option.get("context_quality"),
        "page_years": option.get("page_years") or [],
        "page_value_multiplier": option.get("page_value_multiplier"),
        "page_statement_unit": option.get("page_statement_unit"),
        "page_monetary_basis": option.get("page_monetary_basis"),
    }


def main() -> int:
    rows = []
    for symbol, period in TARGETS:
        try:
            package = build_review(symbol, period)
            review = package.get("review") or {}
            doc = package.get("document") or {}
            source_url = str(doc.get("url") or review.get("source_url") or "")
            certification = certify_fundamental_source(symbol, source_url)
            options = [
                _compact_option(item)
                for item in (review.get("fields", {}).get("net_income") or [])
            ]
            rows.append({
                "symbol": symbol,
                "fiscal_period": period,
                "as_of": doc.get("as_of"),
                "source_url": source_url,
                "certification": certification,
                "parse_valid": (package.get("parse") or {}).get("valid"),
                "source_document_sha256": (package.get("parse") or {}).get("source_document_sha256"),
                "preferred_column": review.get("preferred_column"),
                "preferred_column_evidence": review.get("preferred_column_evidence"),
                "net_income_candidates": options,
            })
        except Exception as exc:
            rows.append({
                "symbol": symbol,
                "fiscal_period": period,
                "error": f"{type(exc).__name__}:{exc}",
            })
    print(json.dumps({"read_only": True, "targets": len(TARGETS), "rows": rows}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
