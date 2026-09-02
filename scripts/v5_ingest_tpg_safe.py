"""Bounded production ingestion for TPG annual audited statements.

This is intentionally NOT a generic auto-ingester. It only permits C.A. Telares
de Palo Grande (TPG), periods 2024-12-31 and 2025-12-31, when all gates pass.
Already validated allowlisted periods are frozen and never re-ingested by this
script, protecting production snapshots from future parser changes.

published_at remains None unless a separate official publication chain supplies it,
so these snapshots may support current analysis but not point-in-time backtests.
"""
from __future__ import annotations

import asyncio
import json

from database import FundamentalSnapshot, SessionLocal
from services.fundamental_autoreview_v5 import propose_fail_closed_selections
from services.fundamental_collector_v5 import coverage_report, ingest_normalized_report
from services.fundamental_discovery_v5 import discover_documents
from services.fundamental_document_metadata_v5 import fetch_official_pdf_document_metadata
from services.fundamental_pdf_parser_v5 import fetch_and_parse_official_pdf
from services.fundamental_review_v5 import build_review_package, select_candidates

SYMBOL = "TPG"
ALLOWED_AS_OF = {"2024-12-31", "2025-12-31"}
EXPECTED_PERIODS = 2


def _audited_link(text: str) -> bool:
    low = " ".join(str(text or "").lower().split())
    return "estado" in low and "financier" in low and "audit" in low


def _existing_validated_periods() -> set[str]:
    with SessionLocal() as db:
        rows = db.query(FundamentalSnapshot.as_of).filter(
            FundamentalSnapshot.simbolo == SYMBOL,
            FundamentalSnapshot.validated.is_(True),
            FundamentalSnapshot.as_of.in_(sorted(ALLOWED_AS_OF)),
        ).all()
        return {str(row[0]) for row in rows if row and row[0]}


async def main_async() -> dict:
    existing = _existing_validated_periods()
    if existing == ALLOWED_AS_OF:
        return {
            "ok": True,
            "symbol": SYMBOL,
            "allowlisted_periods": sorted(ALLOWED_AS_OF),
            "accepted_periods": sorted(existing),
            "accepted_count": len(existing),
            "skipped": "all_allowlisted_periods_already_validated_and_frozen",
            "rows": [],
        }

    missing_periods = ALLOWED_AS_OF - existing
    discovery = await discover_documents(SYMBOL, timeout=15.0)
    if not discovery.get("ok"):
        return {"ok": False, "error": "discovery_failed", "discovery": discovery, "rows": []}

    docs = [
        d for d in discovery.get("documents") or []
        if d.get("kind") == "pdf" and _audited_link(str(d.get("text") or ""))
    ]
    rows = []
    seen_sha: set[str] = set()

    for doc in docs:
        url = str(doc.get("url") or "")
        text = str(doc.get("text") or "")
        candidates, parse_meta = await asyncio.to_thread(fetch_and_parse_official_pdf, SYMBOL, url, 20.0)
        if not parse_meta.get("valid"):
            rows.append({"url": url, "accepted": False, "error": "parse_invalid", "reason": parse_meta.get("reason")})
            continue
        digest = str(parse_meta.get("source_document_sha256") or "")
        if not digest or digest in seen_sha:
            rows.append({"url": url, "accepted": False, "duplicate_document_sha": bool(digest), "sha256": digest})
            continue
        seen_sha.add(digest)

        doc_meta = await asyncio.to_thread(fetch_official_pdf_document_metadata, SYMBOL, url, 20.0)
        as_of = str(doc_meta.get("as_of") or "")
        if as_of not in ALLOWED_AS_OF:
            rows.append({"url": url, "sha256": digest, "accepted": False, "error": "period_not_allowlisted", "as_of": as_of})
            continue
        if as_of in existing:
            rows.append({"url": url, "sha256": digest, "as_of": as_of, "accepted": True, "frozen_existing": True})
            continue
        if as_of not in missing_periods:
            continue
        if doc_meta.get("currency") != "VES" or doc_meta.get("monetary_basis") != "constant_ves_end_period":
            rows.append({
                "url": url, "sha256": digest, "accepted": False,
                "error": "currency_or_basis_unresolved",
                "currency": doc_meta.get("currency"), "monetary_basis": doc_meta.get("monetary_basis"),
                "metadata_unresolved": doc_meta.get("unresolved") or [],
            })
            continue

        review = build_review_package(
            SYMBOL, candidates, source_url=url, as_of=as_of,
            source_document_sha256=digest,
        )
        proposal = propose_fail_closed_selections(review)
        if not proposal.get("valid"):
            rows.append({
                "url": url, "sha256": digest, "as_of": as_of,
                "accepted": False, "error": "autoreview_not_unambiguous",
                "missing_required": proposal.get("missing_required") or [],
            })
            continue

        record, selected_meta = select_candidates(
            review,
            proposal.get("selections") or {},
            extra_fields={"currency": "VES", "monetary_basis": "constant_ves_end_period"},
        )
        if not selected_meta.get("valid"):
            rows.append({"url": url, "sha256": digest, "as_of": as_of, "accepted": False, "error": "selection_failed"})
            continue
        coverage = coverage_report(SYMBOL, record)
        if coverage.get("coverage_pct", 0) < 100.0:
            rows.append({
                "url": url, "sha256": digest, "as_of": as_of,
                "accepted": False, "error": "required_coverage_not_complete", "coverage": coverage,
            })
            continue

        year = as_of[:4]
        metadata = {
            "review_gate": "bounded_tpg_official_audited_link_selection",
            "selected_evidence": selected_meta.get("evidence", {}),
            "preferred_column_evidence": review.get("preferred_column_evidence"),
            "source_document_sha256": digest,
            "document_metadata_evidence": doc_meta,
            "audit_evidence": {
                "source": "official_issuer_link_text",
                "text": text[:300],
                "discovery_source_url": discovery.get("source_url"),
            },
            "review_required": False,
            "backtest_eligible": False,
            "backtest_blocker": "published_at_required_from_official_publication_chain",
        }
        result = ingest_normalized_report(
            SYMBOL, record, source_url=url, as_of=as_of,
            document_type="annual_audited", fiscal_period=f"FY{year}",
            audited=True, published_at=None, metadata=metadata,
            period_start=f"{year}-01-01", hydrate_fx=True, require_fx=True,
        )
        rows.append({
            "url": url, "sha256": digest, "as_of": as_of,
            "accepted": bool(result.get("accepted")),
            "persisted": bool(result.get("persisted")),
            "duplicate": bool(result.get("duplicate")),
            "coverage": result.get("coverage"), "validation": result.get("validation"),
            "fx": result.get("fx"), "document_id": result.get("document_id"),
            "snapshot_id": result.get("snapshot_id"), "error": result.get("error"),
        })

    final_periods = _existing_validated_periods()
    return {
        "ok": final_periods == ALLOWED_AS_OF,
        "symbol": SYMBOL,
        "allowlisted_periods": sorted(ALLOWED_AS_OF),
        "accepted_periods": sorted(final_periods),
        "accepted_count": len(final_periods),
        "frozen_existing_at_start": sorted(existing),
        "rows": rows,
    }


def main() -> int:
    report = asyncio.run(main_async())
    with open("v5_tpg_ingest.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, default=str)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
