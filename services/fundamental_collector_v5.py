"""Collector/ingestion layer for Caracas Bull V5 fundamentals.

Acquisition, accounting validation and FX normalization are separate concerns.
Production ingestion is fail-closed for the *fundamental datum*, never for the
listed asset. Certified sources (issuer/BVC/SUNAVAL) are tier A; secondary HTTPS
sources for registered issuers are tier B and may feed the fundamental score
with lower confidence. Controlled fixtures may disable the FX gate explicitly.
"""
from __future__ import annotations

from typing import Any

from services.fundamental_certifier_policy_v5 import classify_fundamental_source
from services.fundamental_sources_v5 import get_source, source_audit_summary
from services.fundamental_store_v5 import save_snapshot, validate_snapshot
from services.fx_history_v5 import attach_historical_bcv_fx
from services.fx_normalization_v5 import normalize_to_usd, validate_fx_metadata

REQUIRED_BY_TYPE = {
    "financial": {"total_assets", "equity", "net_income"},
    "non_financial": {"total_assets", "equity", "net_income"},
    "investment_vehicle": {"equity", "total_assets"},
}


def normalize_record(symbol: str, record: dict[str, Any]) -> dict[str, Any]:
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


def _prepare_fx(record: dict, *, as_of: str, fiscal_period: str | None,
                period_start: str | None, hydrate_fx: bool) -> tuple[dict, dict]:
    out = dict(record)
    currency = str(out.get("currency") or "").upper().strip()
    if currency in {"USD", "US$"}:
        normalized, meta = normalize_to_usd(out)
        return normalized, meta
    if currency not in {"VES", "BS", "BS."}:
        return out, {"valid": False, "flags": ["unsupported_or_missing_currency"]}

    fx_meta = validate_fx_metadata(out)
    if hydrate_fx and not fx_meta.get("valid"):
        out, history_meta = attach_historical_bcv_fx(
            out,
            as_of=as_of,
            fiscal_period=fiscal_period,
            period_start=period_start,
            refresh_if_missing=True,
        )
    else:
        history_meta = {"ok": bool(fx_meta.get("valid")), "skipped": True}

    normalized, final_meta = normalize_to_usd(out)
    final_meta["history_resolution"] = history_meta
    return normalized, final_meta


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
    period_start: str | None = None,
    hydrate_fx: bool = True,
    require_fx: bool = True,
) -> dict:
    """Production entry point for tier-A or tier-B fundamental evidence.

    Failure rejects only this fundamental snapshot. It does not make the listed
    asset ineligible for market/technical scoring.
    """
    evidence = classify_fundamental_source(symbol, source_url)
    if not evidence.get("admissible"):
        return {
            "accepted": False,
            "asset_evaluable": True,
            "fundamental_available": False,
            "coverage": coverage_report(symbol, record),
            "validation": {"valid": False, "score": 0.0, "notes": ["fuente fundamental no admisible"]},
            "fx": {"valid": False, "flags": ["not_evaluated_due_to_source_gate"]},
            "certification": evidence,
            "persisted": False,
            "error": "fundamental_source_not_admissible",
        }

    normalized = normalize_record(symbol, record)
    normalized["fundamental_evidence_tier"] = evidence.get("evidence_tier")
    normalized["fundamental_evidence_confidence"] = evidence.get("evidence_confidence")
    normalized["fundamental_source_certified"] = bool(evidence.get("certified"))
    normalized, fx = _prepare_fx(
        normalized,
        as_of=as_of,
        fiscal_period=fiscal_period,
        period_start=period_start,
        hydrate_fx=hydrate_fx,
    )

    if require_fx and not fx.get("valid"):
        return {
            "accepted": False,
            "asset_evaluable": True,
            "fundamental_available": False,
            "coverage": coverage_report(symbol, normalized),
            "validation": {"valid": False, "score": 0.0, "notes": ["FX histórico requerido"]},
            "fx": fx,
            "certification": evidence,
            "persisted": False,
            "error": "historical_fx_required",
        }

    coverage = coverage_report(symbol, normalized)
    validation = validate_snapshot(symbol, normalized, source_url, as_of)
    if not validation.get("valid"):
        return {
            "accepted": False,
            "asset_evaluable": True,
            "fundamental_available": False,
            "coverage": coverage,
            "validation": validation,
            "fx": fx,
            "certification": evidence,
            "persisted": False,
        }

    meta = dict(metadata or {})
    meta["fx_validation"] = fx
    meta["source_certifier_v5"] = evidence.get("certifier")
    meta["source_certifier_route_v5"] = evidence.get("route")
    meta["source_certifier_policy_version_v5"] = evidence.get("policy_version")
    meta["fundamental_evidence_tier_v5"] = evidence.get("evidence_tier")
    meta["fundamental_evidence_confidence_v5"] = evidence.get("evidence_confidence")
    meta["fundamental_source_certified_v5"] = bool(evidence.get("certified"))
    persisted = save_snapshot(
        symbol,
        normalized,
        source_url=source_url,
        as_of=as_of,
        document_type=document_type,
        fiscal_period=fiscal_period,
        audited=audited,
        published_at=published_at,
        metadata=meta,
    )
    accepted = bool(persisted.get("saved") or persisted.get("duplicate"))
    return {
        "accepted": accepted,
        "asset_evaluable": True,
        "fundamental_available": accepted,
        "coverage": coverage,
        "validation": validation,
        "fx": fx,
        "certification": evidence,
        "persisted": bool(persisted.get("saved")),
        "duplicate": bool(persisted.get("duplicate")),
        "document_id": persisted.get("document_id"),
        "snapshot_id": persisted.get("snapshot_id"),
    }


def audit_universe(symbols: list[str]) -> dict:
    return source_audit_summary([str(s).upper() for s in symbols])
