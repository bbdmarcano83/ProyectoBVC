"""Diagnóstico read-only de TDV.D FY2025 desde la publicación certificada BVC."""
from __future__ import annotations

import json

from scripts.fundamental_backfill_v5 import build_review
from services.fundamental_autoreview_v5 import propose_fail_closed_selections


def main() -> int:
    package = build_review("TDV.D", "FY2025")
    review = package["review"]
    proposal = propose_fail_closed_selections(review)
    fields = {}
    for name in ("total_assets", "total_liabilities", "equity", "net_income", "operating_cash_flow"):
        fields[name] = [
            {
                "index": row.get("index"),
                "value": row.get("value"),
                "page": row.get("page"),
                "column_index": row.get("column_index"),
                "alias": row.get("alias"),
                "evidence": row.get("evidence"),
            }
            for row in (review.get("fields", {}).get(name) or [])
        ]
    out = {
        "document": package["document"],
        "parse": package["parse"],
        "preferred_column": review.get("preferred_column"),
        "proposal": proposal,
        "fields": fields,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if package["parse"].get("valid") else 2


if __name__ == "__main__":
    raise SystemExit(main())
