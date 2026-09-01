"""CLI persistente para backfill IBC V5.

No existe modo dry-run. Requiere DATABASE_URL externa y persiste únicamente
puntos que pasan la política de fuentes; nunca degrada cierres BVC oficiales.
"""
from __future__ import annotations

import argparse
import json

from services.ibc_backfill_v5 import backfill_range


def main() -> int:
    parser = argparse.ArgumentParser(description="Caracas Bull V5 IBC persistent backfill")
    parser.add_argument("--from-year", type=int, required=True)
    parser.add_argument("--from-month", type=int, required=True)
    parser.add_argument("--to-year", type=int, required=True)
    parser.add_argument("--to-month", type=int, required=True)
    args = parser.parse_args()

    result = backfill_range(
        args.from_year,
        args.from_month,
        args.to_year,
        args.to_month,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
