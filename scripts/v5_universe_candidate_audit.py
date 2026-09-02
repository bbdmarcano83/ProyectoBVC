"""Read-only audit of automatically discoverable PDF candidates for V5 issuers.

No figures are persisted. The script ranks official PDF links, parses evidence,
and reports whether the existing fail-closed auto-review can resolve the required
accounting fields. Missing period/currency/basis metadata remains a hard blocker.
"""
from __future__ import annotations

import asyncio
import json

from services.fundamental_autoreview_v5 import propose_fail_closed_selections
from services.fundamental_discovery_v5 import discover_documents
from services.fundamental_pdf_parser_v5 import fetch_and_parse_official_pdf
from services.fundamental_review_v5 import build_review_package
from services.fundamental_sources_v5 import SOURCE_REGISTRY
from services.fundamental_store_v5 import load_latest_validated


def _score(doc: dict) -> tuple[int, str]:
    text = f"{doc.get('text','')} {doc.get('url','')}".lower()
    score = 0
    for word, points in (
        ("audit", 10), ("estado", 8), ("financ", 8), ("anual", 6),
        ("informe", 4), ("balance", 4), ("2026", 6), ("2025", 5),
        ("2024", 4), ("2023", 3), ("2022", 2),
    ):
        if word in text:
            score += points
    if str(doc.get("kind")) == "pdf":
        score += 20
    return score, str(doc.get("url") or "")


def _sample_candidates(candidates: dict) -> dict:
    out = {}
    for field, options in (candidates or {}).items():
        rows = []
        for option in (options or [])[:3]:
            rows.append({
                "value": option.get("value"),
                "raw": option.get("raw"),
                "page": option.get("page"),
                "alias": option.get("alias"),
                "column_index": option.get("column_index"),
                "evidence": str(option.get("evidence") or "")[:260],
            })
        out[field] = {"count": len(options or []), "sample": rows}
    return out


async def _attempt_pdf(symbol: str, doc: dict, sem: asyncio.Semaphore) -> dict:
    url = str(doc.get("url") or "")
    async with sem:
        candidates, meta = await asyncio.to_thread(fetch_and_parse_official_pdf, symbol, url, 15.0)
    attempt = {
        "url": url,
        "text": doc.get("text"),
        "parse_valid": bool(meta.get("valid")),
        "reason": meta.get("reason"),
        "fields_with_candidates": int(meta.get("fields_with_candidates") or 0),
        "sha256": meta.get("source_document_sha256"),
        "pages": meta.get("pages"),
    }
    if meta.get("valid"):
        attempt["candidate_fields"] = _sample_candidates(candidates)
        review = build_review_package(
            symbol, candidates, source_url=url, as_of="candidate",
            source_document_sha256=meta.get("source_document_sha256"),
        )
        proposal = propose_fail_closed_selections(review)
        attempt["autoreview_valid"] = bool(proposal.get("valid"))
        attempt["missing_required"] = proposal.get("missing_required") or []
        attempt["selected_fields"] = sorted((proposal.get("selections") or {}).keys())
    return attempt


async def _one_symbol(symbol: str, validated: set[str], sem: asyncio.Semaphore) -> dict:
    if symbol in validated:
        return {"symbol": symbol, "skipped": "already_validated"}
    disc = await discover_documents(symbol, timeout=12.0)
    docs = sorted((disc.get("documents") or []), key=_score, reverse=True)
    pdfs = [d for d in docs if d.get("kind") == "pdf"][:2]
    attempts = await asyncio.gather(*(_attempt_pdf(symbol, doc, sem) for doc in pdfs)) if pdfs else []
    return {
        "symbol": symbol,
        "discovery_ok": bool(disc.get("ok")),
        "discovery_error": disc.get("error"),
        "discovered": int(disc.get("count") or 0),
        "ranked_pdf_candidates": len(pdfs),
        "parse_valid_candidates": sum(1 for a in attempts if a.get("parse_valid")),
        "autoreview_ready_candidates": sum(1 for a in attempts if a.get("autoreview_valid")),
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
