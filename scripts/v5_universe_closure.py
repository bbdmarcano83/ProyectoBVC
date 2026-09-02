"""Read-only production closure audit for the complete Caracas Bull V5 universe.

The report distinguishes source registration from actual usable fundamentals.
It never upgrades missing data: gaps remain explicit and fail-closed.
This script is intentionally safe to run repeatedly against production Neon.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict
from typing import Any

from database import DB_PERSISTENCE_MODE, FundamentalDocument, FundamentalSnapshot, SessionLocal
from services.fundamental_discovery_v5 import discover_documents
from services.fundamental_sources_v5 import SOURCE_REGISTRY
from services.fundamental_store_v5 import load_latest_validated


def _json(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _sha(meta: dict) -> bool:
    value = str(meta.get("source_document_sha256") or "").strip().lower()
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def _fx_valid(row: dict) -> bool:
    if not row:
        return False
    if row.get("fx_valid_v5") is not None:
        return bool(row.get("fx_valid_v5"))
    currency = str(row.get("currency") or "").upper().strip()
    if currency in {"USD", "US$"}:
        return True
    meta = row.get("fx_validation") or row.get("fx") or {}
    return bool(meta.get("valid")) if isinstance(meta, dict) else False


async def _discover(symbols: list[str]) -> dict[str, dict]:
    sem = asyncio.Semaphore(6)
    async def one(symbol: str):
        async with sem:
            try:
                result = await discover_documents(symbol, timeout=15.0)
            except Exception as exc:
                result = {"symbol": symbol, "ok": False, "error": type(exc).__name__, "documents": []}
            return symbol, result
    pairs = await asyncio.gather(*(one(s) for s in symbols))
    return dict(pairs)


def build_report(*, with_discovery: bool = False) -> dict:
    symbols = sorted(SOURCE_REGISTRY)
    with SessionLocal() as db:
        docs = db.query(FundamentalDocument).filter(FundamentalDocument.simbolo.in_(symbols)).all()
        snaps = db.query(FundamentalSnapshot).filter(FundamentalSnapshot.simbolo.in_(symbols)).all()

    docs_by: dict[str, list] = defaultdict(list)
    snaps_by: dict[str, list] = defaultdict(list)
    for row in docs:
        docs_by[str(row.simbolo).upper()].append(row)
    for row in snaps:
        snaps_by[str(row.simbolo).upper()].append(row)

    latest, latest_meta = load_latest_validated()
    latest = latest if isinstance(latest, dict) else {}
    discovery = asyncio.run(_discover(symbols)) if with_discovery else {}

    rows = []
    for symbol in symbols:
        src = SOURCE_REGISTRY[symbol]
        drows = docs_by.get(symbol, [])
        srows = snaps_by.get(symbol, [])
        valid_snaps = [s for s in srows if bool(s.validated)]
        sha_docs = 0
        published_docs = 0
        for d in drows:
            meta = _json(d.metadata_json)
            sha_docs += int(_sha(meta))
            published_docs += int(bool(str(d.published_at or "").strip()))
        record = latest.get(symbol) or {}
        history_periods = int(record.get("history_periods_usd") or 0) if isinstance(record, dict) else 0
        history_dates = list(record.get("history_dates_usd") or []) if isinstance(record, dict) else []
        fx_ok = _fx_valid(record if isinstance(record, dict) else {})
        fundamentals_ready = bool(record) and bool(valid_snaps)
        provenance_ready = bool(drows) and sha_docs > 0 and published_docs > 0
        trend_ready = history_periods >= 3
        analysis_ready = fundamentals_ready and fx_ok
        backtest_ready = analysis_ready and provenance_ready
        disc = discovery.get(symbol, {}) if with_discovery else {}
        rows.append({
            "symbol": symbol,
            "issuer": src.get("issuer"),
            "industry_type": src.get("industry_type"),
            "source_status": src.get("status"),
            "source_confidence": int(src.get("confidence") or 0),
            "documents": len(drows),
            "documents_with_sha256": sha_docs,
            "documents_with_published_at": published_docs,
            "snapshots": len(srows),
            "validated_snapshots": len(valid_snaps),
            "latest_validated_as_of": record.get("as_of") if isinstance(record, dict) else None,
            "fx_valid": fx_ok,
            "history_periods_usd": history_periods,
            "history_dates_usd": history_dates,
            "fundamentals_ready": fundamentals_ready,
            "trend_ready_3p": trend_ready,
            "provenance_ready": provenance_ready,
            "analysis_ready": analysis_ready,
            "backtest_ready": backtest_ready,
            "discovery_ok": bool(disc.get("ok")) if with_discovery else None,
            "discovered_documents": int(disc.get("count") or 0) if with_discovery else None,
            "discovery_error": disc.get("error") if with_discovery else None,
        })

    def n(key: str) -> int:
        return sum(1 for row in rows if row.get(key))

    return {
        "database_mode": DB_PERSISTENCE_MODE,
        "universe_symbols": len(symbols),
        "registered_sources": len(symbols),
        "symbols_with_any_document": sum(1 for r in rows if r["documents"] > 0),
        "symbols_with_validated_snapshot": sum(1 for r in rows if r["validated_snapshots"] > 0),
        "symbols_with_fx_valid": n("fx_valid"),
        "symbols_with_usd_history_3p": n("trend_ready_3p"),
        "symbols_provenance_ready": n("provenance_ready"),
        "symbols_analysis_ready": n("analysis_ready"),
        "symbols_backtest_ready": n("backtest_ready"),
        "symbols_discovery_ok": n("discovery_ok") if with_discovery else None,
        "symbols_with_discovered_documents": sum(1 for r in rows if (r.get("discovered_documents") or 0) > 0) if with_discovery else None,
        "latest_loader_meta": latest_meta,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--output", default="v5_universe_closure.json")
    parser.add_argument("--require-analysis-ready", type=int, default=0)
    args = parser.parse_args()
    report = build_report(with_discovery=args.discover)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, default=str)
    summary = {k: v for k, v in report.items() if k not in {"rows", "latest_loader_meta"}}
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    if args.require_analysis_ready and report["symbols_analysis_ready"] < args.require_analysis_ready:
        print(json.dumps({"closure_gate": "not_ready", "required": args.require_analysis_ready, "actual": report["symbols_analysis_ready"]}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
