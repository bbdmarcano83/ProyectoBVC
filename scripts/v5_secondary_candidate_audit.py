"""Read-only audit of curated tier-B fundamental evidence.

No figures are persisted. The audit downloads only URLs admitted by the curated
secondary registry, re-checks redirects, fingerprints exact bytes, extracts PDF
metadata/candidates and runs the same fail-closed accounting auto-review used for
primary evidence. A failed secondary document affects only fundamental coverage;
the listed asset remains evaluable.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from urllib.parse import urlparse

import httpx

from services.fundamental_autoreview_v5 import propose_fail_closed_selections
from services.fundamental_certifier_policy_v5 import classify_fundamental_source
from services.fundamental_document_metadata_v5 import extract_document_metadata_from_pdf_bytes
from services.fundamental_pdf_parser_v5 import MAX_PDF_BYTES, parse_pdf_bytes
from services.fundamental_review_v5 import build_review_package
from services.fundamental_secondary_discovery_v5 import discover_secondary_documents
from services.fundamental_secondary_sources_v5 import SECONDARY_SOURCE_REGISTRY
from services.fundamental_store_v5 import load_latest_validated


def _tier_b(symbol: str, url: str) -> dict | None:
    evidence = classify_fundamental_source(symbol, url)
    return evidence if evidence.get("admissible") and evidence.get("evidence_tier") == "B_SECONDARY" else None


def _score(doc: dict) -> tuple[int, str]:
    text = f"{doc.get('text','')} {doc.get('url','')}".lower()
    score = 20 if doc.get("kind") == "pdf" else 0
    for word, points in (("estados financieros", 30), ("audit", 20), ("balance", 12), ("financ", 8), ("2025", 6), ("2024", 5), ("2023", 4), ("2022", 3)):
        if word in text:
            score += points
    return score, str(doc.get("url") or "")


async def _download_pdf(symbol: str, url: str, timeout: float, sem: asyncio.Semaphore) -> tuple[bytes | None, dict]:
    evidence = _tier_b(symbol, url)
    if not evidence:
        return None, {"valid": False, "reason": "source_not_curated_tier_b"}
    headers = {
        "User-Agent": "CaracasBull-FundamentalAudit/1.0 (+curated-secondary-audit)",
        "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.5",
    }
    async with sem:
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
                response = await client.get(url)
                response.raise_for_status()
        except Exception as exc:
            return None, {"valid": False, "reason": f"download_error:{type(exc).__name__}"}
    final_url = str(response.url)
    final_evidence = _tier_b(symbol, final_url)
    if not final_evidence:
        return None, {"valid": False, "reason": "redirect_not_curated_tier_b", "final_url": final_url}
    data = bytes(response.content or b"")
    digest = hashlib.sha256(data).hexdigest()
    ctype = str(response.headers.get("content-type") or "").lower()
    if not data.startswith(b"%PDF"):
        return None, {
            "valid": False, "reason": "download_not_pdf", "final_url": final_url,
            "bytes": len(data), "content_type": ctype, "sha256": digest,
        }
    if len(data) > MAX_PDF_BYTES:
        return None, {"valid": False, "reason": "pdf_too_large", "bytes": len(data), "sha256": digest}
    return data, {
        "valid": True,
        "final_url": final_url,
        "bytes": len(data),
        "content_type": ctype,
        "sha256": digest,
        "evidence": final_evidence,
    }


def _selected_multiplier(review: dict, proposal: dict) -> tuple[float | None, str | None]:
    fields = review.get("fields") or {}
    multipliers: set[float] = set()
    missing = False
    for field, idx in (proposal.get("selections") or {}).items():
        option = next((o for o in (fields.get(field) or []) if int(o.get("index", -1)) == int(idx)), None)
        if option is None:
            return None, "selected_candidate_missing"
        value = option.get("page_value_multiplier")
        if value is None:
            missing = True
            continue
        try:
            multipliers.add(float(value))
        except (TypeError, ValueError):
            return None, "invalid_page_multiplier"
    if len(multipliers) > 1:
        return None, "conflicting_page_multipliers"
    if not multipliers:
        return (None, "unit_not_explicit") if missing else (1.0, None)
    return next(iter(multipliers)), None


async def _attempt(symbol: str, doc: dict, sem: asyncio.Semaphore) -> dict:
    url = str(doc.get("url") or "")
    data, download = await _download_pdf(symbol, url, 20.0, sem)
    attempt = {
        "url": url,
        "source_name": doc.get("source_name"),
        "route": doc.get("route"),
        "registered_confidence": doc.get("confidence"),
        "rank_score": _score(doc)[0],
        "download": download,
        "parse_valid": False,
        "metadata_resolved": False,
        "autoreview_valid": False,
        "analysis_ingest_ready": False,
    }
    if data is None:
        return attempt

    candidates, parse_meta = parse_pdf_bytes(data)
    document_meta = extract_document_metadata_from_pdf_bytes(data)
    attempt["parse_valid"] = bool(parse_meta.get("valid"))
    attempt["parse_meta"] = parse_meta
    attempt["document_metadata"] = document_meta
    attempt["metadata_resolved"] = bool(document_meta.get("resolved"))
    if not parse_meta.get("valid"):
        return attempt

    review = build_review_package(
        symbol,
        candidates,
        source_url=download.get("final_url") or url,
        as_of=str(document_meta.get("as_of") or "candidate"),
        source_document_sha256=download.get("sha256"),
    )
    proposal = propose_fail_closed_selections(review)
    attempt["autoreview"] = proposal
    attempt["autoreview_valid"] = bool(proposal.get("valid"))
    multiplier, unit_error = _selected_multiplier(review, proposal) if proposal.get("valid") else (None, "autoreview_not_valid")
    attempt["value_multiplier"] = multiplier
    attempt["unit_error"] = unit_error
    attempt["analysis_ingest_ready"] = bool(
        proposal.get("valid")
        and document_meta.get("resolved")
        and multiplier is not None
        and _tier_b(symbol, str(download.get("final_url") or url))
    )
    return attempt


async def _one(symbol: str, validated: set[str], sem: asyncio.Semaphore) -> dict:
    # Tier A already persisted always wins; no reason to spend network/CI on B.
    if symbol in validated:
        return {"symbol": symbol, "skipped": "already_has_validated_fundamental"}
    discovery = await discover_secondary_documents(symbol, timeout=12.0)
    pdfs = sorted([d for d in (discovery.get("documents") or []) if d.get("kind") == "pdf"], key=_score, reverse=True)[:4]
    attempts = await asyncio.gather(*(_attempt(symbol, doc, sem) for doc in pdfs)) if pdfs else []
    return {
        "symbol": symbol,
        "discovery": {k: v for k, v in discovery.items() if k != "documents"},
        "pdf_candidates": len(pdfs),
        "parseable": sum(1 for a in attempts if a.get("parse_valid")),
        "autoreview_ready": sum(1 for a in attempts if a.get("autoreview_valid")),
        "metadata_ready": sum(1 for a in attempts if a.get("metadata_resolved")),
        "analysis_ingest_ready": sum(1 for a in attempts if a.get("analysis_ingest_ready")),
        "attempts": attempts,
    }


async def main_async() -> dict:
    latest, _ = load_latest_validated()
    validated = set((latest or {}).keys())
    symbols = sorted(SECONDARY_SOURCE_REGISTRY)
    sem = asyncio.Semaphore(4)
    rows = await asyncio.gather(*(_one(symbol, validated, sem) for symbol in symbols))
    return {
        "symbols_with_curated_secondary_sources": len(symbols),
        "skipped_existing_validated": sum(1 for r in rows if r.get("skipped")),
        "symbols_with_secondary_pdf": sum(1 for r in rows if r.get("pdf_candidates", 0) > 0),
        "symbols_with_parseable_secondary_pdf": sum(1 for r in rows if r.get("parseable", 0) > 0),
        "symbols_with_secondary_autoreview": sum(1 for r in rows if r.get("autoreview_ready", 0) > 0),
        "symbols_secondary_analysis_ingest_ready": sum(1 for r in rows if r.get("analysis_ingest_ready", 0) > 0),
        "rows": rows,
    }


def main() -> int:
    report = asyncio.run(main_async())
    with open("v5_secondary_candidates.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
