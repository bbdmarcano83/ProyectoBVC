"""Read-only audit for BVC WordPress/SharePoint financial evidence.

Targets issuers whose registered fundamental source falls back to the BVC. It
searches the official WordPress REST API, preserves publication timestamps,
downloads only explicitly linked artifacts, and parses PDF artifacts without
persisting any accounting figures. Image-only bundles remain blocked until a
reproducible OCR worker supplies evidence.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from services.bvc_attachment_adapter_v5 import (
    build_evidence_bundle,
    discover_bvc_wp_notices,
    download_notice_artifacts,
)
from services.fundamental_autoreview_v5 import propose_fail_closed_selections
from services.fundamental_pdf_parser_v5 import parse_pdf_bytes
from services.fundamental_review_v5 import build_review_package
from services.fundamental_sources_v5 import SOURCE_REGISTRY


FINANCIAL_HINTS = (
    "estado financiero", "estados financieros", "audit", "balance", "resultado",
    "informe anual", "informe financiero", "ejercicio", "accionistas", "asamblea",
)
NEGATIVE_HINTS = ("dividendo", "precio", "negociacion", "negociación", "suspension", "suspensión")


def _queries(symbol: str, src: dict[str, Any]) -> list[str]:
    issuer = str(src.get("issuer") or "").strip()
    queries = [symbol]
    # Short issuer labels work better with WordPress search than legal names.
    cleaned = re.sub(r"\b(?:c\.a\.|s\.a\.c\.a\.|s\.a\.|banco universal)\b", " ", issuer, flags=re.I)
    cleaned = re.sub(r"[^A-Za-zÁÉÍÓÚáéíóúÑñ0-9 ]+", " ", cleaned)
    cleaned = " ".join(cleaned.split())
    if cleaned:
        queries.append(cleaned)
        queries.append(" ".join(cleaned.split()[:3]))
    known = {
        "TDV.D": ["CANTV"],
        "MPA": ["MANPA"],
        "RST": ["Ron Santa Teresa"],
        "GMC.B": ["Grupo Mantra"],
        "FNC": ["Fábrica Nacional de Cementos", "FNC"],
        "FNV": ["Fábrica Nacional de Vidrio", "FNV"],
        "PGR": ["Proagro"],
        "PTN": ["Protinal"],
        "VNA.B": ["Venealternative"],
        "BVCC": ["Bolsa de Valores de Caracas"],
    }
    queries.extend(known.get(symbol, []))
    out: list[str] = []
    seen: set[str] = set()
    for query in queries:
        q = " ".join(str(query).split()).strip()
        if len(q) < 3 or q.lower() in seen:
            continue
        seen.add(q.lower())
        out.append(q)
    return out[:5]


def _notice_score(notice: dict[str, Any]) -> int:
    text = f"{notice.get('title','')} {notice.get('notice_url','')}".lower()
    score = sum(12 for hint in FINANCIAL_HINTS if hint in text)
    score -= sum(10 for hint in NEGATIVE_HINTS if hint in text)
    score += min(8, int(notice.get("artifact_count") or 0) * 2)
    return score


async def _audit_notice(symbol: str, notice: dict[str, Any], sem: asyncio.Semaphore) -> dict[str, Any]:
    async with sem:
        downloaded = await download_notice_artifacts(notice, timeout=18.0)
    artifacts = downloaded.get("artifacts") or []
    bundle = build_evidence_bundle(notice, artifacts)
    row: dict[str, Any] = {
        "notice_id": notice.get("notice_id"),
        "notice_url": notice.get("notice_url"),
        "title": notice.get("title"),
        "published_at": notice.get("published_at"),
        "artifact_urls": notice.get("artifact_urls") or [],
        "artifact_count": len(artifacts),
        "download_ok": bool(downloaded.get("ok")),
        "download_errors": downloaded.get("errors") or [],
        "bundle_valid": bool(bundle.get("valid")),
        "bundle_error": bundle.get("error"),
        "artifact_set_sha256": bundle.get("artifact_set_sha256"),
        "image_only": bundle.get("image_only"),
        "artifacts": bundle.get("artifacts") or [],
        "pdf_attempts": [],
    }
    for artifact in artifacts:
        candidates, meta = parse_pdf_bytes(artifact.data)
        if not artifact.data.startswith(b"%PDF"):
            continue
        attempt = {
            "source_url": artifact.final_url,
            "sha256": meta.get("source_document_sha256"),
            "parse_valid": bool(meta.get("valid")),
            "pages": meta.get("pages"),
            "fields_with_candidates": meta.get("fields_with_candidates"),
            "autoreview_valid": False,
            "missing_required": [],
        }
        if meta.get("valid"):
            review = build_review_package(
                symbol,
                candidates,
                source_url=str(artifact.final_url),
                as_of="candidate",
                source_document_sha256=meta.get("source_document_sha256"),
            )
            proposal = propose_fail_closed_selections(review)
            attempt.update({
                "autoreview_valid": bool(proposal.get("valid")),
                "missing_required": proposal.get("missing_required") or [],
                "selected_fields": sorted((proposal.get("selections") or {}).keys()),
                "preferred_column": review.get("preferred_column"),
                "preferred_column_evidence": review.get("preferred_column_evidence"),
                "method": proposal.get("method"),
            })
        row["pdf_attempts"].append(attempt)
    return row


async def _one_symbol(symbol: str, src: dict[str, Any], sem: asyncio.Semaphore) -> dict[str, Any]:
    query_rows = []
    notices_by_url: dict[str, dict[str, Any]] = {}
    for query in _queries(symbol, src):
        result = await discover_bvc_wp_notices(query, timeout=15.0, per_page=30)
        query_rows.append({"query": query, "ok": result.get("ok"), "error": result.get("error"), "count": result.get("count", 0)})
        for notice in result.get("notices") or []:
            url = str(notice.get("notice_url") or "")
            if url:
                notices_by_url[url] = notice
    ranked = sorted(notices_by_url.values(), key=lambda n: (_notice_score(n), str(n.get("published_at") or "")), reverse=True)
    # Keep a bounded set of likely financial notices; audit remains read-only.
    selected = [n for n in ranked if _notice_score(n) > 0][:5]
    audited = await asyncio.gather(*(_audit_notice(symbol, n, sem) for n in selected)) if selected else []
    return {
        "symbol": symbol,
        "issuer": src.get("issuer"),
        "source_type": src.get("source_type"),
        "queries": query_rows,
        "notices_found": len(ranked),
        "financial_notices_selected": len(selected),
        "notices_with_published_at": sum(1 for n in selected if n.get("published_at")),
        "notices_with_downloaded_artifacts": sum(1 for n in audited if n.get("artifact_count", 0) > 0),
        "notices_with_valid_bundle": sum(1 for n in audited if n.get("bundle_valid")),
        "notices_image_only_blocked": sum(1 for n in audited if n.get("bundle_error") == "ocr_required_for_image_only_document"),
        "notices_with_parseable_pdf": sum(1 for n in audited if any(a.get("parse_valid") for a in n.get("pdf_attempts") or [])),
        "notices_with_autoreview_pdf": sum(1 for n in audited if any(a.get("autoreview_valid") for a in n.get("pdf_attempts") or [])),
        "notices": audited,
    }


async def main_async() -> dict[str, Any]:
    targets = {
        symbol: src for symbol, src in SOURCE_REGISTRY.items()
        if str(src.get("source_type") or "") == "bvc_primary_fallback"
    }
    sem = asyncio.Semaphore(4)
    rows = await asyncio.gather(*(_one_symbol(symbol, targets[symbol], sem) for symbol in sorted(targets)))
    return {
        "target_symbols": len(targets),
        "symbols_with_notices": sum(1 for r in rows if r["notices_found"] > 0),
        "symbols_with_financial_notices": sum(1 for r in rows if r["financial_notices_selected"] > 0),
        "symbols_with_published_notice": sum(1 for r in rows if r["notices_with_published_at"] > 0),
        "symbols_with_artifacts": sum(1 for r in rows if r["notices_with_downloaded_artifacts"] > 0),
        "symbols_with_valid_bundle": sum(1 for r in rows if r["notices_with_valid_bundle"] > 0),
        "symbols_image_only_blocked": sum(1 for r in rows if r["notices_image_only_blocked"] > 0),
        "symbols_with_parseable_pdf": sum(1 for r in rows if r["notices_with_parseable_pdf"] > 0),
        "symbols_with_autoreview_pdf": sum(1 for r in rows if r["notices_with_autoreview_pdf"] > 0),
        "rows": rows,
    }


def main() -> int:
    report = asyncio.run(main_async())
    with open("v5_bvc_attachment_audit.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
