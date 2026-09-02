"""Backfill allowlistado de períodos certificados bloqueados sólo por FX.

Las cifras no se modifican ni se hardcodean aquí. Cada período vuelve a pasar por
parser, auto-review, certificador (emisor/BVC/SUNAVAL), validación contable y
normalización FX histórica antes de poder persistirse en Neon.
"""
from __future__ import annotations

import json

from scripts.fundamental_backfill_v5 import auto_persist

TARGETS = (
    ("DOM", "FY2022"),
    ("ENV", "FY2022"),
    ("FNV", "FY2022"),
    ("GZL", "FY2023"),
    ("PGR", "FY2022"),
)


def main() -> int:
    rows = []
    for symbol, fiscal_period in TARGETS:
        try:
            row = auto_persist(symbol, fiscal_period)
        except Exception as exc:
            rows.append({
                "symbol": symbol,
                "fiscal_period": fiscal_period,
                "accepted": False,
                "persisted": False,
                "error": f"{type(exc).__name__}:{exc}",
            })
            continue
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        rows.append({
            "symbol": symbol,
            "fiscal_period": fiscal_period,
            "accepted": bool(result.get("accepted")),
            "persisted": bool(result.get("persisted")),
            "duplicate": bool(result.get("duplicate")),
            "document_id": result.get("document_id"),
            "snapshot_id": result.get("snapshot_id"),
            "certification": result.get("certification"),
            "fx": result.get("fx"),
            "coverage": result.get("coverage"),
            "validation": result.get("validation"),
            "error": result.get("error"),
        })

    accepted = sum(1 for row in rows if row.get("accepted"))
    report = {
        "targets": len(TARGETS),
        "accepted": accepted,
        "all_accepted": accepted == len(TARGETS),
        "rows": rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["all_accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
