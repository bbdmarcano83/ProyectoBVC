"""Read-only audit of automatically discoverable PDF candidates for V5 issuers.

No figures are persisted. The script ranks official PDF links, parses evidence,
checks fail-closed accounting auto-review, and independently resolves fiscal /
monetary metadata from visible PDF text. Metadata remains a hard blocker until
all required pieces are explicit.
"""
from __future__ import annotations

import asyncio
import json

from services.fundamental_autoreview_v5 import propose_fail_closed_selections
from services.fundamental_discovery_v5 import discover_documents
from services.fundamental_document_metadata_v5 import fetch_official_pdf_document_metadata
from services.fundamental_pdf_parser_v5 import fetch_and_parse_official_pdf
from services.fundamental_review_v5 import build_review_package
from services.fundamental_sources_v5 import SOURCE_REGISTRY
from services.fundamental_store_v5 import load_latest_validated


def _score(doc: dict) -> tuple[int, str]:
    text = f"{doc.get('text','')} {doc.get('url','')}".lower()
    score = 0
    for word, points in (
        ("estados financieros", 30), ("estado financiero", 24),
        ("audit", 18), ("informe auditor", 16), ("contadores independientes", 16),
        ("balance", 12), ("informe anual", 10), ("financ", 8), ("anual", 6),
        ("2026", 7), ("2025", 6), ("2024", 5), ("2023", 4), ("2022", 3),
    ):
        if word in text:
            score += points
    for word, points in (
        ("manual", -35), ("codigo-de-etica", -35), ("código de ética", -35),
        ("politicas", -25), ("políticas", -25), ("terminos", -20), ("términos", -20),
        ("folleto", -18), ("prospecto", -12), ("convocatoria", -18),
        ("comisiones", -25), ("carta poder", -25),
    ):
        if word in text:
            score += points
    if str(doc.get("kind")) == "pdf":
        score += 20
    score += min(2, int(doc.get("discovery_depth") or 0))
    return score, str(doc.get("url") or "")


def _sample_candidates(candidates: dict) -> dict:
    out = {}
    for field, options in (candidates or {}).items():
        rows = []
        for option in (options or [])[:4]:
            rows.append({
                "value": option.get("value"),
                "raw": option.get("raw"),
                "page": option.get("page"),
                "alias": option.get("alias"),
                "column_index": option.get("column_index"),
                "context_quality": option.get("context_quality"),
                "page_years": option.get("page_years") or [],
                "derived_from": option.get("derived_from") or [],
                "evidence": str(option.get("evidence") or "")[:300],
            })
        out[field] = {"count": len(options or []), "sample": rows}
    return out


async def _attempt_pdf(symbol: str, doc: dict, sem: asyncio.Semaphore) -> dict:
    url = str(doc.get("url") or "")
    async with sem:
        parsed_task = asyncio.to_thread(fetch_and_parse_official_pdf, symbol, url, 15.0)
        metadata_task = asyncio.to_thread(fetch_official_pdf_document_metadata, symbol, url, 15.0)
        (candidates, meta), document_meta = await asyncio.gather(parsed_task, metadata_task)
    attempt = {
        "url": url,
        "text": doc.get("text"),
        "rank_score": _score(doc)[0],
        "discovery_depth": doc.get("discovery_depth"),
        "parse_valid": bool(meta.get("valid")),
        "reason": meta.get("reason"),
        "fields_with_candidates": int(meta.get("fields_with_candidates") or 0),
        "derived_accounting_candidates": int(meta.get("derived_accounting_candidates") or 0),
        "sha256": meta.get("source_document_sha256"),
        "pages": meta.get("pages"),
        "document_metadata": document_meta,
        "metadata_resolved": bool(document_meta.get("resolved")),
        "metadata_unresolved": document_meta.get("unresolved") or [],
    }
    if meta.get("valid"):
        attempt["candidate_fields"] = _sample_candidates(candidates)
        review = build_review_package(
            symbol, candidates, source_url=url,
            as_of=str(document_meta.get("as_of") or "candidate"),
            source_document_sha256=meta.get("source_document_sha256"),
        )
        proposal = propose_fail_closed_selections(review)
        attempt["preferred_column"] = review.get("preferred_column")
        attempt["preferred_column_evidence"] = review.get("preferred_column_evidence")
        attempt["autoreview_valid"] = bool(proposal.get("valid"))
        attempt["autoreview_method"] = proposal.get("method")
        attempt["balance_page"] = proposal.get("balance_page")
        attempt["missing_required"] = proposal.get("missing_required") or []
        attempt["selected_fields"] = sorted((proposal.get("selections") or {}).keys())
        attempt["analysis_ingest_ready"] = bool(proposal.get("valid") and document_meta.get("resolved"))
        attempt["backtest_ingest_ready"] = False
        attempt["backtest_blocker"] = "published_at_required_from_official_publication_chain"
    return attempt


async def _one_symbol(symbol: str, validated: set[str], sem: asyncio.Semaphore) -> dict:
    if symbol in validated:
        return {"symbol": symbol, "skipped": "already_validated"}
    disc = await discover_documents(symbol, timeout=12.0)
    docs = sorted((disc.get("documents") or []), key=_score, reverse=True)
    pdfs = [d for d in docs if d.get("kind") == "pdf"][:3]
    attempts = await asyncio.gather(*(_attempt_pdf(symbol, doc, sem) for doc in pdfs)) if pdfs else []
    return {
        "symbol": symbol,
        "discovery_ok": bool(disc.get("ok")),
        "discovery_error": disc.get("error"),
        "discovered": int(disc.get("count") or 0),
        "visited_pages": int(disc.get("visited_pages") or 0),
        "ranked_pdf_candidates": len(pdfs),
        "parse_valid_candidates": sum(1 for a in attempts if a.get("parse_valid")),
        "autoreview_ready_candidates": sum(1 for a in attempts if a.get("autoreview_valid")),
        "metadata_ready_candidates": sum(1 for a in attempts if a.get("metadata_resolved")),
        "analysis_ingest_ready_candidates": sum(1 for a in attempts if a.get("analysis_ingest_ready")),
        "attempts": attempts,
    }


async def main_async() -> dict:
    latest, _ = load_latest_validated()
    validated = set((latest or {}).keys())
    sem = asyncio.Semaphore(6)
    rows = await asyncio.gather(*(_one_symbol(s, validated, sem) for s in sorted(SOURCE_REGISTRY)))
    return {
        "symbols": len(SOURCE_REGISTRY),
        "already_validated": sum(1 for r in rows if r.get("skipped")),
        "symbols_with_pdf_candidates": sum(1 for r in rows if r.get("ranked_pdf_candidates", 0) > 0),
        "symbols_with_parseable_pdf": sum(1 for r in rows if r.get("parse_valid_candidates", 0) > 0),
        "symbols_with_autoreview_candidate": sum(1 for r in rows if r.get("autoreview_ready_candidates", 0) > 0),
        "symbols_with_metadata_candidate": sum(1 for r in rows if r.get("metadata_ready_candidates", 0) > 0),
        "symbols_analysis_ingest_ready": sum(1 for r in rows if r.get("analysis_ingest_ready_candidates", 0) > 0),
        "rows": rows,
    }


def main() -> int:
    report = asyncio.run(main_async())
    with open("v5_universe_candidates.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({k:v for k,v in report.items() if k != "rows"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
