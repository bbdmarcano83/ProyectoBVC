"""Read-only production closure audit for the complete Caracas Bull V5 universe.

The report separates asset evaluability from fundamental-data availability.
Missing, incomplete or technically invalid fundamentals remain explicit, but do
not block a registered BVC-universe asset from market/risk scoring. Fail-closed
continues to apply to each fundamental datum and to fundamental/backtest claims.
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
from services.fx_normalization_v5 import validate_fx_metadata


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
    return bool(validate_fx_metadata(row).get("valid"))


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
        fundamentals_available = bool(record) and bool(valid_snaps)
        fundamental_ready = fundamentals_available and fx_ok
        provenance_ready = bool(drows) and sha_docs > 0 and published_docs > 0
        trend_ready = history_periods >= 3

        # Fundamental closure is no longer the eligibility gate for the asset.
        # Every registered universe symbol remains evaluable; missing/invalid
        # fundamentals simply contribute no fundamental pillar until resolved.
        asset_evaluable = True
        analysis_ready = asset_evaluable  # compatibility alias with new semantics
        fundamental_backtest_ready = fundamental_ready and provenance_ready

        if fundamental_ready:
            fundamental_status = "AVAILABLE"
        elif fundamentals_available and not fx_ok:
            fundamental_status = "PENDING_FX"
        elif valid_snaps:
            fundamental_status = "PENDING_VALIDATION"
        elif drows:
            fundamental_status = "DOCUMENT_PRESENT_NO_USABLE_SNAPSHOT"
        else:
            fundamental_status = "NOT_AVAILABLE"

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
            "fundamentals_ready": fundamentals_available,  # legacy key: snapshot availability
            "fundamental_ready_for_scoring": fundamental_ready,
            "fundamental_status": fundamental_status,
            "trend_ready_3p": trend_ready,
            "provenance_ready": provenance_ready,
            "asset_evaluable": asset_evaluable,
            "analysis_ready": analysis_ready,
            "fundamental_backtest_ready": fundamental_backtest_ready,
            "backtest_ready": fundamental_backtest_ready,  # legacy fundamental-backtest meaning
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
        "symbols_asset_evaluable": n("asset_evaluable"),
        "symbols_analysis_ready": n("analysis_ready"),  # compatibility alias
        "symbols_with_any_document": sum(1 for r in rows if r["documents"] > 0),
        "symbols_with_validated_snapshot": sum(1 for r in rows if r["validated_snapshots"] > 0),
        "symbols_fundamental_ready_for_scoring": n("fundamental_ready_for_scoring"),
        "symbols_without_usable_fundamental": sum(1 for r in rows if not r["fundamental_ready_for_scoring"]),
        "symbols_with_fx_valid": n("fx_valid"),
        "symbols_with_usd_history_3p": n("trend_ready_3p"),
        "symbols_provenance_ready": n("provenance_ready"),
        "symbols_fundamental_backtest_ready": n("fundamental_backtest_ready"),
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
    parser.add_argument("--require-analysis-ready", type=int, default=0, help="Legacy alias: minimum registered/evaluable assets")
    parser.add_argument("--require-asset-evaluable", type=int, default=0)
    parser.add_argument("--require-fundamental-ready", type=int, default=0)
    args = parser.parse_args()
    report = build_report(with_discovery=args.discover)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, default=str)
    summary = {k: v for k, v in report.items() if k not in {"rows", "latest_loader_meta"}}
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))

    required_assets = max(args.require_analysis_ready, args.require_asset_evaluable)
    if required_assets and report["symbols_asset_evaluable"] < required_assets:
        print(json.dumps({"closure_gate": "assets_not_evaluable", "required": required_assets, "actual": report["symbols_asset_evaluable"]}))
        return 2
    if args.require_fundamental_ready and report["symbols_fundamental_ready_for_scoring"] < args.require_fundamental_ready:
        print(json.dumps({"closure_gate": "fundamental_coverage_below_target", "required": args.require_fundamental_ready, "actual": report["symbols_fundamental_ready_for_scoring"]}))
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
