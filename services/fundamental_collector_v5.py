"""Collector/ingestion layer for Caracas Bull V5 fundamentals.

This module intentionally separates acquisition from interpretation. Network
adapters may discover/download official reports, but only normalized records
that pass source and accounting validation are persisted.
"""
from __future__ import annotations

from typing import Any

from services.fundamental_sources_v5 import get_source, source_audit_summary
from services.fundamental_store_v5 import save_snapshot, validate_snapshot

REQUIRED_BY_TYPE = {
    "financial": {"total_assets", "equity", "net_income"},
    "non_financial": {"total_assets", "equity", "net_income"},
    "investment_vehicle": {"equity", "total_assets"},
}


def normalize_record(symbol: str, record: dict[str, Any]) -> dict[str, Any]:
    """Normalize field names without inventing absent values."""
    out = dict(record or {})
    aliases = {
        "assets": "total_assets",
        "liabilities": "total_liabilities",
        "debt": "total_debt",
        "net_profit": "net_income",
        "profit": "net_income",
        "shareholders_equity": "equity",
        "operating_cashflow": "operating_cash_flow",
        "ppe": "net_ppe",
        "shares": "shares_outstanding",
        "nav_ps": "nav_per_share",
    }
    for old, new in aliases.items():
        if new not in out and old in out:
            out[new] = out[old]

    src = get_source(symbol)
    if src and not out.get("industry_type"):
        out["industry_type"] = src.get("industry_type")
    return out


def coverage_report(symbol: str, record: dict[str, Any]) -> dict:
    symbol = str(symbol or "").upper().strip()
    src = get_source(symbol)
    if not src:
        return {"symbol": symbol, "registered": False, "coverage_pct": 0.0, "missing": []}
    normalized = normalize_record(symbol, record)
    kind = str(src.get("industry_type") or "")
    required = REQUIRED_BY_TYPE.get(kind, set())
    present = {k for k in required if normalized.get(k) not in (None, "")}
    missing = sorted(required - present)
    pct = round(len(present) / max(1, len(required)) * 100.0, 1)
    return {
        "symbol": symbol,
        "registered": True,
        "canonical_symbol": src.get("canonical_symbol"),
        "industry_type": kind,
        "coverage_pct": pct,
        "missing": missing,
        "source_confidence": int(src.get("confidence", 0)),
        "source_status": src.get("status"),
    }


def ingest_normalized_report(
    symbol: str,
    record: dict[str, Any],
    *,
    source_url: str,
    as_of: str,
    document_type: str,
    fiscal_period: str | None = None,
    audited: bool = False,
    published_at: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Single write entry point for collectors and future admin imports."""
    normalized = normalize_record(symbol, record)
    coverage = coverage_report(symbol, normalized)
    validation = validate_snapshot(symbol, normalized, source_url, as_of)
    if not validation.get("valid"):
        return {
            "accepted": False,
            "coverage": coverage,
            "validation": validation,
            "persisted": False,
        }

    persisted = save_snapshot(
        symbol,
        normalized,
        source_url=source_url,
        as_of=as_of,
        document_type=document_type,
        fiscal_period=fiscal_period,
        audited=audited,
        published_at=published_at,
        metadata=metadata,
    )
    return {
        "accepted": bool(persisted.get("saved") or persisted.get("duplicate")),
        "coverage": coverage,
        "validation": validation,
        "persisted": bool(persisted.get("saved")),
        "duplicate": bool(persisted.get("duplicate")),
        "document_id": persisted.get("document_id"),
        "snapshot_id": persisted.get("snapshot_id"),
    }


def audit_universe(symbols: list[str]) -> dict:
    """Report source-registry coverage for the live BVC universe."""
    return source_audit_summary([str(s).upper() for s in symbols])
