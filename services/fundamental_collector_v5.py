"""Collector/persistence contract for Caracas Bull V5 fundamentals.

This module deliberately does NOT scrape arbitrary pages. It receives an
already-extracted snapshot tied to a registered official source, validates it,
and persists both provenance and normalized data. Only validated snapshots may
feed V5.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from database import SessionLocal, FundamentalDocument, FundamentalSnapshot
from services.fundamental_sources_v5 import get_source


NUMERIC_FIELDS = {
    "market_cap", "total_debt", "cash", "ebit", "net_income", "equity",
    "total_assets", "total_liabilities", "revenue", "free_cash_flow",
    "current_assets", "current_liabilities", "net_ppe", "shares_outstanding",
    "nav", "nav_per_share", "market_price", "distribution_yield_pct",
}
SERIES_FIELDS = {
    "earnings_history", "revenue_history", "fcf_history", "nav_history",
    "distributions_history",
}


def _f(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def document_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def normalize_snapshot(data: dict) -> dict:
    """Keep only supported fields; missing values stay missing."""
    out: dict[str, Any] = {}
    for key in NUMERIC_FIELDS:
        value = _f(data.get(key))
        if value is not None:
            out[key] = value
    for key in SERIES_FIELDS:
        value = data.get(key)
        if isinstance(value, list):
            clean = [_f(x) for x in value]
            out[key] = [x for x in clean if x is not None]
    for key in ("currency", "as_of", "source", "industry_type", "sector"):
        if data.get(key) not in (None, ""):
            out[key] = data.get(key)
    return out


def validate_snapshot(symbol: str, data: dict, source_confidence: int | None = None) -> dict:
    """Fail-closed validation; returns score/flags without mutating input."""
    src = get_source(symbol)
    flags: list[str] = []
    if not src:
        flags.append("unregistered_source")
        industry_type = str(data.get("industry_type") or "unknown")
        confidence = int(source_confidence or 0)
    else:
        industry_type = str(src.get("industry_type") or "unknown")
        confidence = int(source_confidence if source_confidence is not None else src.get("confidence", 0))

    normalized = normalize_snapshot(data)
    score = 100.0

    if confidence < 80:
        flags.append("source_confidence_below_80")
        score -= 30
    if not normalized.get("as_of"):
        flags.append("missing_as_of")
        score -= 20

    assets = _f(normalized.get("total_assets"))
    liabilities = _f(normalized.get("total_liabilities"))
    equity = _f(normalized.get("equity"))
    identity_error_pct = None
    if assets is not None and liabilities is not None and equity is not None and abs(assets) > 1e-12:
        identity_error_pct = abs(assets - (liabilities + equity)) / abs(assets) * 100.0
        if identity_error_pct > 2.0:
            flags.append("accounting_identity_error_gt_2pct")
            score -= min(40.0, identity_error_pct)
    else:
        flags.append("accounting_identity_not_checkable")
        score -= 10

    if industry_type == "financial":
        required = ("total_assets", "equity", "net_income")
    elif industry_type == "investment_vehicle":
        required = ("equity", "total_assets")
        if not any(k in normalized for k in ("nav", "nav_per_share", "market_cap")):
            flags.append("vehicle_missing_nav_or_market_value")
            score -= 15
    else:
        required = ("total_assets", "equity", "net_income", "revenue")

    missing_required = [k for k in required if normalized.get(k) is None]
    if missing_required:
        flags.append("missing_required:" + ",".join(missing_required))
        score -= min(40.0, len(missing_required) * 10.0)

    for key in ("total_assets", "equity", "market_cap", "shares_outstanding"):
        value = _f(normalized.get(key))
        if value is not None and value < 0:
            flags.append(f"negative_{key}")
            score -= 15

    score = round(max(0.0, min(100.0, score)), 1)
    blocking = {
        "unregistered_source", "source_confidence_below_80",
        "accounting_identity_error_gt_2pct",
    }
    validated = score >= 70 and not any(f in blocking for f in flags)
    return {
        "validated": validated,
        "validation_score": score,
        "validation_flags": flags,
        "accounting_identity_error_pct": None if identity_error_pct is None else round(identity_error_pct, 4),
        "industry_type": industry_type,
        "normalized": normalized,
    }


def ingest_snapshot(
    *,
    symbol: str,
    source_url: str,
    document_type: str,
    fiscal_period: str,
    as_of: str,
    data: dict,
    document_content: bytes,
    audited: bool = False,
    published_at: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Validate + persist one official document snapshot idempotently."""
    symbol = str(symbol or "").upper().strip()
    src = get_source(symbol)
    if not src:
        return {"persisted": False, "validated": False, "error": "unregistered_source", "symbol": symbol}
    if not source_url.startswith("https://"):
        return {"persisted": False, "validated": False, "error": "source_url_must_be_https", "symbol": symbol}

    payload = dict(data or {})
    payload["as_of"] = as_of
    payload["source"] = source_url
    payload["industry_type"] = src.get("industry_type")
    check = validate_snapshot(symbol, payload, int(src.get("confidence", 0)))
    digest = document_sha256(document_content)

    with SessionLocal() as db:
        existing_doc = db.query(FundamentalDocument).filter(FundamentalDocument.document_hash == digest).first()
        if existing_doc:
            existing_snap = db.query(FundamentalSnapshot).filter(
                FundamentalSnapshot.document_id == existing_doc.id,
                FundamentalSnapshot.simbolo == symbol,
            ).first()
            return {
                "persisted": False,
                "duplicate": True,
                "validated": bool(existing_snap.validated) if existing_snap else False,
                "document_id": existing_doc.id,
                "snapshot_id": existing_snap.id if existing_snap else None,
                "symbol": symbol,
            }

        doc = FundamentalDocument(
            simbolo=symbol,
            issuer=src.get("issuer"),
            source_url=source_url,
            source_type=src.get("source_type", "unknown"),
            source_confidence=int(src.get("confidence", 0)),
            document_type=document_type,
            fiscal_period=fiscal_period,
            as_of=as_of,
            audited=bool(audited),
            document_hash=digest,
            published_at=published_at,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True),
        )
        db.add(doc)
        db.flush()

        normalized = dict(check["normalized"])
        normalized["validation_flags"] = check["validation_flags"]
        normalized["accounting_identity_error_pct"] = check["accounting_identity_error_pct"]
        snap = FundamentalSnapshot(
            document_id=doc.id,
            simbolo=symbol,
            industry_type=check["industry_type"],
            as_of=as_of,
            validated=bool(check["validated"]),
            validation_score=float(check["validation_score"]),
            validation_notes=json.dumps(check["validation_flags"], ensure_ascii=False),
            data_json=json.dumps(normalized, ensure_ascii=False, sort_keys=True),
        )
        db.add(snap)
        db.commit()
        db.refresh(snap)
        return {
            "persisted": True,
            "duplicate": False,
            "validated": bool(snap.validated),
            "validation_score": snap.validation_score,
            "validation_flags": check["validation_flags"],
            "document_id": doc.id,
            "snapshot_id": snap.id,
            "symbol": symbol,
        }


def load_latest_validated_from_db() -> tuple[dict[str, dict], dict]:
    """Return the newest validated snapshot per symbol from Neon/SQLAlchemy."""
    out: dict[str, dict] = {}
    with SessionLocal() as db:
        rows = db.query(FundamentalSnapshot).filter(FundamentalSnapshot.validated.is_(True)).order_by(
            FundamentalSnapshot.simbolo.asc(),
            FundamentalSnapshot.as_of.desc(),
            FundamentalSnapshot.created_at.desc(),
        ).all()
        for row in rows:
            if row.simbolo in out:
                continue
            try:
                payload = json.loads(row.data_json)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(payload, dict):
                continue
            payload["industry_type"] = row.industry_type
            payload["as_of"] = row.as_of
            payload["validation_score"] = row.validation_score
            out[row.simbolo] = payload
    return out, {"source": "database:fundamental_snapshots", "available": bool(out), "count": len(out)}
