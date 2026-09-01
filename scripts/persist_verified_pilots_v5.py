"""Persiste en Neon los tres snapshots piloto V5 ya verificados manualmente.

No es un fixture ciego: cada registro conserva fuente oficial, evidencia,
periodo, base monetaria y pasa por el mismo collector con FX historico,
validacion contable y persistencia idempotente usado por produccion.
"""
from __future__ import annotations

import json

from database import DB_PERSISTENCE_MODE, FundamentalDocument, FundamentalSnapshot, engine
from services.fundamental_collector_v5 import ingest_normalized_report
from services.fundamental_pilots_v5 import PILOTS


def _ensure_v5_fundamental_schema() -> None:
    """Crea únicamente las tablas fundamentales V5 faltantes, de forma idempotente."""
    FundamentalDocument.__table__.create(bind=engine, checkfirst=True)
    FundamentalSnapshot.__table__.create(bind=engine, checkfirst=True)


def persist_verified_pilots() -> dict:
    if DB_PERSISTENCE_MODE != "external":
        raise RuntimeError("external_database_required_for_verified_pilots")

    _ensure_v5_fundamental_schema()

    rows = []
    for symbol, pilot in PILOTS.items():
        data = dict(pilot.get("data") or {})
        # El reporte MSF 2T-2026 informa utilidad acumulada del semestre;
        # por eso la tasa promedio debe cubrir 01-ene..30-jun, no solo Q2.
        period_start = "2026-01-01" if symbol == "MVZ.A" else None
        result = ingest_normalized_report(
            symbol,
            data,
            source_url=str(pilot["source_url"]),
            as_of=str(pilot["as_of"]),
            document_type=str(pilot["document_type"]),
            fiscal_period=str(pilot["fiscal_period"]),
            audited=bool(pilot.get("audited")),
            metadata={
                "verified_pilot": True,
                "evidence": pilot.get("evidence"),
                "ingestion_mode": "verified_manual_evidence",
            },
            period_start=period_start,
            hydrate_fx=True,
            require_fx=True,
        )
        rows.append({"symbol": symbol, "result": result})

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
    return 0 if result["accepted"] == len(PILOTS) else 2


if __name__ == "__main__":
    raise SystemExit(main())
