"""CLI para backfill IBC V5.

Por defecto es dry-run. ``--persist`` escribe sólo puntos que pasan la política
de fuente y nunca degrada cierres BVC oficiales ya almacenados.
"""
from __future__ import annotations

import argparse
import json

from services.ibc_backfill_v5 import backfill_range


def main() -> int:
    parser = argparse.ArgumentParser(description="Caracas Bull V5 IBC backfill")
    parser.add_argument("--from-year", type=int, required=True)
    parser.add_argument("--from-month", type=int, required=True)
    parser.add_argument("--to-year", type=int, required=True)
    parser.add_argument("--to-month", type=int, required=True)
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()

    result = backfill_range(
        args.from_year,
        args.from_month,
        args.to_year,
        args.to_month,
        persist=args.persist,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
