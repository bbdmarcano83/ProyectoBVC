"""Backfill regulatorio V5 para documentos avalados por emisor/BVC/SUNAVAL.

No escribe cifras manuales: descarga el PDF, genera candidatos, auto-revisa de
forma fail-closed y persiste sólo si pasa cobertura, contabilidad y FX histórico.
"""
from __future__ import annotations

import json

from database import DB_PERSISTENCE_MODE, FundamentalDocument, FundamentalSnapshot, engine
from services.fundamental_autoreview_v5 import propose_fail_closed_selections
from services.fundamental_pdf_parser_v5 import fetch_and_parse_official_pdf
from services.fundamental_regulatory_manifest_v5 import REGULATORY_BACKFILL_V5
from services.fundamental_review_v5 import build_review_package, accept_reviewed_snapshot


def _require_external_db() -> None:
    if DB_PERSISTENCE_MODE != "external":
        raise RuntimeError("external_database_required_for_regulatory_backfill")


def _ensure_schema() -> None:
    FundamentalDocument.__table__.create(bind=engine, checkfirst=True)
    FundamentalSnapshot.__table__.create(bind=engine, checkfirst=True)


def ingest_document(symbol: str, doc: dict) -> dict:
    candidates, parse_meta = fetch_and_parse_official_pdf(symbol, doc["url"])
    if not parse_meta.get("valid"):
        return {"symbol": symbol, "period": doc["fiscal_period"], "accepted": False, "persisted": False, "stage": "parse", "parse": parse_meta}

    review = build_review_package(
        symbol,
        candidates,
        source_url=doc["url"],
        as_of=doc["as_of"],
        source_document_sha256=parse_meta.get("source_document_sha256"),
    )
    proposal = propose_fail_closed_selections(review)
    if not proposal.get("valid"):
        return {
            "symbol": symbol,
            "period": doc["fiscal_period"],
            "accepted": False,
            "persisted": False,
            "stage": "autoreview",
            "proposal": proposal,
        }

    result = accept_reviewed_snapshot(
        review,
        proposal["selections"],
        document_type=doc["document_type"],
        fiscal_period=doc["fiscal_period"],
        audited=bool(doc.get("audited")),
        currency=doc.get("currency", "VES"),
        monetary_basis=doc.get("monetary_basis", "nominal_ves"),
        published_at=doc.get("published_at"),
        extra_fields={},
        hydrate_fx=True,
        require_fx=True,
        value_multiplier=float(doc.get("value_multiplier", 1)),
        document_metadata={
            "source_class": "issuer_or_market_authority_verified",
            "regulatory_evidence": doc.get("regulatory_evidence"),
            "discovery_url": doc.get("discovery_url"),
        },
    )
    return {
        "symbol": symbol,
        "period": doc["fiscal_period"],
        "stage": "collector",
        "proposal": proposal,
        "parse": parse_meta,
        "result": result,
        "accepted": bool(result.get("accepted")),
        "persisted": bool(result.get("persisted")),
    }


def main() -> int:
    _require_external_db()
    _ensure_schema()
    rows = []
    for symbol, issuer in REGULATORY_BACKFILL_V5.items():
        for doc in issuer.get("documents", []):
            rows.append(ingest_document(symbol, doc))
    summary = {
        "database_mode": DB_PERSISTENCE_MODE,
        "documents": len(rows),
        "accepted": sum(1 for row in rows if row.get("accepted")),
        "persisted": sum(1 for row in rows if row.get("persisted")),
        "rows": rows,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0 if summary["accepted"] == summary["documents"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
