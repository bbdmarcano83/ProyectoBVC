"""Bounded production ingestion for CGQ FY2025 audited consolidated statements.

Only the exact official issuer PDF and FY2025 are permitted. All accounting,
metadata and historical-FX gates remain fail-closed. published_at is intentionally
left unset until an official publication timestamp is independently recovered.
"""
from __future__ import annotations

import asyncio
import json

from database import FundamentalDocument, FundamentalSnapshot, SessionLocal
from services.fundamental_autoreview_v5 import propose_fail_closed_selections
from services.fundamental_collector_v5 import coverage_report, ingest_normalized_report
from services.fundamental_document_metadata_v5 import fetch_official_pdf_document_metadata
from services.fundamental_pdf_parser_v5 import fetch_and_parse_official_pdf
from services.fundamental_review_v5 import build_review_package, select_candidates

SYMBOL = "CGQ"
URL = "https://www.grupoquimico.com/_files/ugd/ad64a7_db932ce5114c4976b19a711232d0fada.pdf"
AS_OF = "2025-12-31"
FISCAL_PERIOD = "FY2025"


def _json_dict(raw) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    try:
        value = json.loads(str(raw or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _existing_validated_snapshot() -> dict | None:
    """Freeze the exact already-certified period before touching the live PDF.

    The official URL can change bytes after ingestion. A later parser change or
    mutable upstream file must not invalidate the immutable, SHA-addressed Neon
    snapshot that already passed every gate. This only accepts the exact CGQ
    FY2025 source/period and requires its stored PDF fingerprint.
    """
    with SessionLocal() as db:
        row = (
            db.query(FundamentalSnapshot, FundamentalDocument)
            .join(FundamentalDocument, FundamentalDocument.id == FundamentalSnapshot.document_id)
            .filter(
                FundamentalSnapshot.simbolo == SYMBOL,
                FundamentalSnapshot.as_of == AS_OF,
                FundamentalSnapshot.validated.is_(True),
                FundamentalDocument.source_url == URL,
                FundamentalDocument.fiscal_period == FISCAL_PERIOD,
                FundamentalDocument.as_of == AS_OF,
                FundamentalDocument.audited.is_(True),
            )
            .order_by(FundamentalSnapshot.id.desc())
            .first()
        )
        if not row:
            return None
        snapshot, document = row
        metadata = _json_dict(document.metadata_json)
        digest = str(metadata.get("source_document_sha256") or "").strip().lower()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            return None
        return {
            "document_id": int(document.id),
            "snapshot_id": int(snapshot.id),
            "sha256": digest,
            "validation_score": float(snapshot.validation_score or 0),
        }


async def main_async() -> dict:
    existing = _existing_validated_snapshot()
    if existing:
        return {
            "ok": True,
            "symbol": SYMBOL,
            "as_of": AS_OF,
            "fiscal_period": FISCAL_PERIOD,
            "accepted": True,
            "persisted": False,
            "duplicate": True,
            "skipped": "exact_certified_snapshot_already_validated_and_frozen",
            **existing,
        }

    candidates, parse_meta = await asyncio.to_thread(fetch_and_parse_official_pdf, SYMBOL, URL, 20.0)
    if not parse_meta.get("valid"):
        return {"ok": False, "accepted": False, "error": "parse_invalid", "parse": parse_meta}
    digest = str(parse_meta.get("source_document_sha256") or "")
    if len(digest) != 64:
        return {"ok": False, "accepted": False, "error": "missing_sha256"}

    doc_meta = await asyncio.to_thread(fetch_official_pdf_document_metadata, SYMBOL, URL, 20.0)
    required = {
        "as_of": doc_meta.get("as_of") == AS_OF,
        "currency": doc_meta.get("currency") == "VES",
        "basis": doc_meta.get("monetary_basis") == "constant_ves_end_period",
        "audited": doc_meta.get("audited") is True,
    }
    if not all(required.values()):
        return {
            "ok": False, "accepted": False, "error": "document_metadata_gate_failed",
            "required": required, "document_metadata": doc_meta,
        }

    review = build_review_package(
        SYMBOL, candidates, source_url=URL, as_of=AS_OF,
        source_document_sha256=digest,
    )
    proposal = propose_fail_closed_selections(review)
    if not proposal.get("valid"):
        return {
            "ok": False, "accepted": False, "error": "autoreview_not_unambiguous",
            "proposal": proposal,
        }

    record, selected_meta = select_candidates(
        review, proposal.get("selections") or {},
        extra_fields={"currency": "VES", "monetary_basis": "constant_ves_end_period"},
    )
    if not selected_meta.get("valid"):
        return {"ok": False, "accepted": False, "error": "selection_failed", "selection": selected_meta}
    coverage = coverage_report(SYMBOL, record)
    if coverage.get("coverage_pct", 0) < 100.0:
        return {"ok": False, "accepted": False, "error": "required_coverage_not_complete", "coverage": coverage}

    metadata = {
        "review_gate": "bounded_cgq_fy2025_official_audited_pdf",
        "selected_evidence": selected_meta.get("evidence", {}),
        "preferred_column_evidence": review.get("preferred_column_evidence"),
        "source_document_sha256": digest,
        "document_metadata_evidence": doc_meta,
        "review_required": False,
        "backtest_eligible": False,
        "backtest_blocker": "published_at_required_from_official_publication_chain",
    }
    result = ingest_normalized_report(
        SYMBOL,
        record,
        source_url=URL,
        as_of=AS_OF,
        document_type="annual_audited",
        fiscal_period=FISCAL_PERIOD,
        audited=True,
        published_at=None,
        metadata=metadata,
        period_start="2025-01-01",
        hydrate_fx=True,
        require_fx=True,
    )
    return {
        "ok": bool(result.get("accepted")),
        "symbol": SYMBOL,
        "as_of": AS_OF,
        "sha256": digest,
        "accepted": bool(result.get("accepted")),
        "persisted": bool(result.get("persisted")),
        "duplicate": bool(result.get("duplicate")),
        "coverage": result.get("coverage"),
        "validation": result.get("validation"),
        "fx": result.get("fx"),
        "document_id": result.get("document_id"),
        "snapshot_id": result.get("snapshot_id"),
        "error": result.get("error"),
    }


def main() -> int:
    report = asyncio.run(main_async())
    with open("v5_cgq_ingest.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
