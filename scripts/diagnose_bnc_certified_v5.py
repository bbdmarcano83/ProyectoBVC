"""Diagnóstico read-only de los cuatro cierres auditados BNC.

No persiste nada. Expone únicamente candidatos contables del documento oficial,
columna preferida y propuesta fail-closed para resolver ambigüedades por etiqueta.
"""
from __future__ import annotations

import json

from scripts.fundamental_backfill_v5 import build_review
from services.fundamental_autoreview_v5 import propose_fail_closed_selections

PERIODS = ("FY2022", "FY2023", "FY2024", "FY2025")
FIELDS = ("total_assets", "total_liabilities", "equity", "net_income", "operating_cash_flow")


def compact_option(option: dict) -> dict:
    return {
        "index": option.get("index"),
        "value": option.get("value"),
        "page": option.get("page"),
        "column_index": option.get("column_index"),
        "alias": option.get("alias"),
        "evidence": option.get("evidence"),
        "context_quality": option.get("context_quality"),
    }


def diagnose() -> dict:
    rows = []
    for period in PERIODS:
        package = build_review("BNC", period)
        review = package["review"]
        proposal = propose_fail_closed_selections(review)
        rows.append({
            "period": period,
            "document": package["document"],
            "parse": package["parse"],
            "preferred_column": review.get("preferred_column"),
            "proposal": proposal,
            "fields": {
                field: [compact_option(option) for option in (review.get("fields", {}).get(field) or [])]
                for field in FIELDS
            },
        })
    return {"symbol": "BNC", "read_only": True, "rows": rows}


def main() -> int:
    print(json.dumps(diagnose(), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
