"""Persiste en Neon snapshots piloto V5 ya verificados contra fuentes oficiales.

Cada registro conserva fuente, evidencia, período y base monetaria; todos pasan
por el collector común con FX histórico, validación y persistencia idempotente.
"""
from __future__ import annotations

import json

from database import DB_PERSISTENCE_MODE, FundamentalDocument, FundamentalSnapshot, engine
from services.fundamental_collector_v5 import ingest_normalized_report
from services.fundamental_pilots_v5 import HISTORICAL_PILOTS, PILOTS


def _ensure_v5_fundamental_schema() -> None:
    """Crea únicamente las tablas fundamentales V5 faltantes, de forma idempotente."""
    FundamentalDocument.__table__.create(bind=engine, checkfirst=True)
    FundamentalSnapshot.__table__.create(bind=engine, checkfirst=True)


def _ingest(symbol: str, pilot: dict, *, historical: bool) -> dict:
    data = dict(pilot.get("data") or {})
    if symbol == "MVZ.A" and str(pilot.get("fiscal_period")) == "2026-Q2":
        # El reporte 2T-2026 informa utilidad acumulada del semestre.
        period_start = "2026-01-01"
    elif str(pilot.get("fiscal_period") or "").upper().startswith("FY"):
        period_start = f"{str(pilot['as_of'])[:4]}-01-01"
    else:
        period_start = None

    return ingest_normalized_report(
        symbol,
        data,
        source_url=str(pilot["source_url"]),
        as_of=str(pilot["as_of"]),
        document_type=str(pilot["document_type"]),
        fiscal_period=str(pilot["fiscal_period"]),
        audited=bool(pilot.get("audited")),
        metadata={
            "verified_pilot": True,
            "historical_series": bool(historical),
            "evidence": pilot.get("evidence"),
            "ingestion_mode": "verified_manual_evidence",
        },
        period_start=period_start,
        hydrate_fx=True,
        require_fx=True,
    )


def persist_verified_pilots() -> dict:
    if DB_PERSISTENCE_MODE != "external":
        raise RuntimeError("external_database_required_for_verified_pilots")

    _ensure_v5_fundamental_schema()

    rows = []
    for symbol, pilot in PILOTS.items():
        rows.append({
            "symbol": symbol,
            "fiscal_period": pilot.get("fiscal_period"),
            "result": _ingest(symbol, pilot, historical=False),
        })

    for symbol, histories in HISTORICAL_PILOTS.items():
        for pilot in histories:
            rows.append({
                "symbol": symbol,
                "fiscal_period": pilot.get("fiscal_period"),
                "result": _ingest(symbol, pilot, historical=True),
            })

    accepted = sum(1 for row in rows if (row["result"] or {}).get("accepted"))
    persisted = sum(1 for row in rows if (row["result"] or {}).get("persisted"))
    duplicates = sum(1 for row in rows if (row["result"] or {}).get("duplicate"))
    return {
        "database_mode": DB_PERSISTENCE_MODE,
        "documents": len(rows),
        "accepted": accepted,
        "persisted": persisted,
        "duplicates": duplicates,
        "rows": rows,
    }


def main() -> int:
    result = persist_verified_pilots()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["accepted"] == result["documents"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
