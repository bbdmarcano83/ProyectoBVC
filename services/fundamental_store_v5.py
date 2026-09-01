"""Persistencia auditable de fundamentales V5.

Esta capa no scrapea ni adivina datos. Recibe snapshots normalizados, valida
coherencia mínima y guarda solamente registros trazables a una fuente oficial.
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
    "current_assets", "current_liabilities", "net_ppe", "operating_cash_flow",
    "capex", "shares_outstanding", "nav", "distribution_per_share",
}


def _f(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def canonical_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def document_hash(source_url: str, as_of: str, payload: dict) -> str:
    basis = f"{source_url.strip()}|{as_of.strip()}|{canonical_json(payload)}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def validate_snapshot(symbol: str, payload: dict, source_url: str, as_of: str) -> dict:
    """Valida trazabilidad y coherencia contable sin completar faltantes."""
    symbol = str(symbol or "").upper().strip()
    source = get_source(symbol)
    notes: list[str] = []
    score = 100.0

    if not symbol:
        return {"valid": False, "score": 0.0, "notes": ["símbolo vacío"]}
    if not source:
        return {"valid": False, "score": 0.0, "notes": ["fuente oficial no registrada"]}
    if int(source.get("confidence", 0)) < 80:
        return {"valid": False, "score": 0.0, "notes": ["confianza de fuente insuficiente"]}
    if not source_url or not source_url.startswith("https://"):
        return {"valid": False, "score": 0.0, "notes": ["source_url HTTPS requerida"]}
    if not as_of:
        return {"valid": False, "score": 0.0, "notes": ["período as_of requerido"]}
    if not isinstance(payload, dict) or not payload:
        return {"valid": False, "score": 0.0, "notes": ["snapshot vacío"]}

    numeric_present = 0
    for key in NUMERIC_FIELDS:
        if key in payload and payload.get(key) not in (None, ""):
            if _f(payload.get(key)) is None:
                notes.append(f"{key}: no numérico")
                score -= 12
            else:
                numeric_present += 1

    if numeric_present < 3:
        notes.append("cobertura numérica muy baja")
        score -= 25

    assets = _f(payload.get("total_assets"))
    liabilities = _f(payload.get("total_liabilities"))
    equity = _f(payload.get("equity"))
    accounting_error_pct = None
    if assets is not None and liabilities is not None and equity is not None and abs(assets) > 1e-12:
        accounting_error_pct = abs(assets - (liabilities + equity)) / abs(assets) * 100.0
        if accounting_error_pct > 5.0:
            notes.append(f"ecuación contable fuera de tolerancia ({accounting_error_pct:.2f}%)")
            score -= 45
        elif accounting_error_pct > 2.0:
            notes.append(f"ecuación contable con diferencia moderada ({accounting_error_pct:.2f}%)")
            score -= 15

    industry_type = str(payload.get("industry_type") or source.get("industry_type") or "").strip()
    if not industry_type:
        notes.append("industry_type faltante")
        score -= 20

    score = max(0.0, min(100.0, score))
    valid = score >= 70.0 and not any("no numérico" in n for n in notes)
    return {
        "valid": valid,
        "score": round(score, 1),
        "notes": notes,
        "accounting_error_pct": round(accounting_error_pct, 3) if accounting_error_pct is not None else None,
        "industry_type": industry_type,
        "source": source,
    }


def save_snapshot(
    symbol: str,
    payload: dict,
    *,
    source_url: str,
    as_of: str,
    document_type: str,
    fiscal_period: str | None = None,
    audited: bool = False,
    published_at: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Guarda un documento y snapshot idempotentemente por hash."""
    symbol = str(symbol or "").upper().strip()
    validation = validate_snapshot(symbol, payload, source_url, as_of)
    if not validation["valid"]:
        return {"saved": False, "validation": validation}

    source = validation["source"]
    canonical = str(source.get("canonical_symbol") or symbol).upper()
    h = document_hash(source_url, as_of, payload)

    with SessionLocal() as db:
        existing_doc = db.query(FundamentalDocument).filter(FundamentalDocument.document_hash == h).first()
        if existing_doc:
            snap = db.query(FundamentalSnapshot).filter(
                FundamentalSnapshot.document_id == existing_doc.id,
                FundamentalSnapshot.simbolo == canonical,
            ).first()
            return {
                "saved": False,
                "duplicate": True,
                "document_id": existing_doc.id,
                "snapshot_id": snap.id if snap else None,
                "validation": validation,
            }

        doc = FundamentalDocument(
            simbolo=canonical,
            issuer=source.get("issuer"),
            source_url=source_url,
            source_type=source.get("source_type", "issuer_official"),
            source_confidence=int(source.get("confidence", 0)),
            document_type=document_type,
            fiscal_period=fiscal_period or as_of,
            as_of=as_of,
            audited=bool(audited),
            document_hash=h,
            published_at=published_at,
            metadata_json=canonical_json(metadata or {}),
        )
        db.add(doc)
        db.flush()

        normalized = dict(payload)
        normalized["source"] = source_url
        normalized["as_of"] = as_of
        normalized["industry_type"] = validation["industry_type"]
        normalized["source_confidence"] = int(source.get("confidence", 0))
        normalized["document_hash"] = h
        normalized["audited"] = bool(audited)

        snap = FundamentalSnapshot(
            document_id=doc.id,
            simbolo=canonical,
            industry_type=validation["industry_type"],
            as_of=as_of,
            validated=True,
            validation_score=validation["score"],
            validation_notes=canonical_json(validation["notes"]),
            data_json=canonical_json(normalized),
        )
        db.add(snap)
        db.commit()
        db.refresh(doc)
        db.refresh(snap)
        return {
            "saved": True,
            "duplicate": False,
            "document_id": doc.id,
            "snapshot_id": snap.id,
            "validation": validation,
        }


def load_latest_validated() -> tuple[dict[str, dict], dict]:
    """Carga el snapshot validado más reciente de cada símbolo."""
    with SessionLocal() as db:
        rows = db.query(FundamentalSnapshot).filter(FundamentalSnapshot.validated.is_(True)).all()

    latest: dict[str, FundamentalSnapshot] = {}
    for row in rows:
        current = latest.get(row.simbolo)
        if current is None or (str(row.as_of), int(row.id)) > (str(current.as_of), int(current.id)):
            latest[row.simbolo] = row

    payload: dict[str, dict] = {}
    invalid_json = 0
    for symbol, row in latest.items():
        try:
            data = json.loads(row.data_json)
        except (TypeError, json.JSONDecodeError):
            invalid_json += 1
            continue
        if isinstance(data, dict):
            payload[symbol] = data

    return payload, {
        "source": "database:fundamental_snapshots",
        "available": bool(payload),
        "count": len(payload),
        "invalid_json": invalid_json,
    }
