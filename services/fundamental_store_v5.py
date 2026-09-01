"""Persistencia auditable de fundamentales V5.

Esta capa no scrapea ni adivina datos. Recibe snapshots normalizados, valida
coherencia mínima y guarda solamente registros trazables a una fuente oficial.

Para backtests existe un loader separado que respeta `published_at`: un estado
no puede ser visible antes de su fecha real de publicación.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
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


def _iso_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if len(text) != 10:
        return None
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == text else None


def _published_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    direct = _iso_date(text)
    if direct is not None:
        return direct
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.date()


def _valid_sha256(value: Any) -> str | None:
    digest = str(value or "").strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        return None
    return digest


def _metadata_dict(raw: Any) -> dict:
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(str(raw or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def validate_document_dates(as_of: str, published_at: str | None = None) -> dict:
    flags: list[str] = []
    as_of_date = _iso_date(as_of)
    if as_of_date is None:
        flags.append("invalid_as_of_iso_date")

    published_date = None
    if published_at not in (None, ""):
        published_date = _published_date(published_at)
        if published_date is None:
            flags.append("invalid_published_at_iso")
        elif as_of_date is not None and published_date < as_of_date:
            flags.append("published_before_as_of")

    return {
        "valid": not flags,
        "flags": flags,
        "as_of_date": as_of_date.isoformat() if as_of_date else None,
        "published_date": published_date.isoformat() if published_date else None,
    }


def is_document_available_on(published_at: str | None, decision_date: str) -> bool:
    decision = _iso_date(decision_date)
    published = _published_date(published_at)
    return bool(decision and published and published <= decision)


def canonical_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def document_hash(source_url: str, as_of: str, payload: dict) -> str:
    basis = f"{source_url.strip()}|{as_of.strip()}|{canonical_json(payload)}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def validate_snapshot(symbol: str, payload: dict, source_url: str, as_of: str) -> dict:
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
    if _iso_date(as_of) is None:
        return {"valid": False, "score": 0.0, "notes": ["as_of debe ser YYYY-MM-DD"]}
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
    symbol = str(symbol or "").upper().strip()
    validation = validate_snapshot(symbol, payload, source_url, as_of)
    if not validation["valid"]:
        return {"saved": False, "validation": validation}

    date_validation = validate_document_dates(as_of, published_at)
    if not date_validation["valid"]:
        validation = dict(validation)
        validation["valid"] = False
        validation["score"] = 0.0
        validation["notes"] = list(validation.get("notes") or []) + list(date_validation["flags"])
        return {"saved": False, "validation": validation, "date_validation": date_validation}

    source = validation["source"]
    canonical = str(source.get("canonical_symbol") or symbol).upper()
    h = document_hash(source_url, as_of, payload)
    incoming_meta = dict(metadata or {})
    incoming_sha = _valid_sha256(incoming_meta.get("source_document_sha256"))

    with SessionLocal() as db:
        existing_doc = db.query(FundamentalDocument).filter(FundamentalDocument.document_hash == h).first()
        if existing_doc:
            snap = db.query(FundamentalSnapshot).filter(
                FundamentalSnapshot.document_id == existing_doc.id,
                FundamentalSnapshot.simbolo == canonical,
            ).first()
            existing_meta = _metadata_dict(existing_doc.metadata_json)
            existing_sha = _valid_sha256(existing_meta.get("source_document_sha256"))
            if incoming_sha and existing_sha and incoming_sha != existing_sha:
                return {
                    "saved": False,
                    "duplicate": False,
                    "source_document_hash_conflict": True,
                    "document_id": existing_doc.id,
                    "snapshot_id": snap.id if snap else None,
                    "validation": validation,
                    "existing_source_document_sha256": existing_sha,
                    "incoming_source_document_sha256": incoming_sha,
                }

            metadata_enriched = False
            if incoming_sha and not existing_sha:
                existing_meta["source_document_sha256"] = incoming_sha
                metadata_enriched = True
            for key, value in incoming_meta.items():
                if key == "source_document_sha256" or value in (None, ""):
                    continue
                if key not in existing_meta:
                    existing_meta[key] = value
                    metadata_enriched = True
            if metadata_enriched:
                existing_doc.metadata_json = canonical_json(existing_meta)
                db.commit()

            return {
                "saved": False,
                "duplicate": True,
                "metadata_enriched": metadata_enriched,
                "document_id": existing_doc.id,
                "snapshot_id": snap.id if snap else None,
                "validation": validation,
                "source_document_sha256": incoming_sha or existing_sha,
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
            metadata_json=canonical_json(incoming_meta),
        )
        db.add(doc)
        db.flush()

        normalized = dict(payload)
        normalized["source"] = source_url
        normalized["as_of"] = as_of
        normalized["published_at"] = published_at
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
            "source_document_sha256": incoming_sha,
        }


def _latest_payload_from_rows(rows: list[FundamentalSnapshot]) -> tuple[dict[str, dict], int]:
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
    return payload, invalid_json


def load_latest_validated() -> tuple[dict[str, dict], dict]:
    with SessionLocal() as db:
        rows = db.query(FundamentalSnapshot).filter(FundamentalSnapshot.validated.is_(True)).all()

    payload, invalid_json = _latest_payload_from_rows(rows)
    history_meta = {"history_attached_count": 0, "history_2plus_count": 0}
    if payload:
        try:
            from services.fundamental_history_v5 import attach_histories_to_latest
            payload, history_meta = attach_histories_to_latest(payload)
        except Exception as exc:
            history_meta = {
                "history_attached_count": 0,
                "history_2plus_count": 0,
                "error": type(exc).__name__,
            }

    return payload, {
        "source": "database:fundamental_snapshots",
        "available": bool(payload),
        "count": len(payload),
        "invalid_json": invalid_json,
        "history": history_meta,
    }


def load_validated_as_of(decision_date: str, *, require_published_at: bool = True) -> tuple[dict[str, dict], dict]:
    decision = _iso_date(decision_date)
    if decision is None:
        return {}, {
            "source": "database:fundamental_snapshots:no_lookahead",
            "available": False,
            "count": 0,
            "error": "invalid_decision_date",
        }

    with SessionLocal() as db:
        joined = db.query(FundamentalSnapshot, FundamentalDocument).join(
            FundamentalDocument,
            FundamentalDocument.id == FundamentalSnapshot.document_id,
        ).filter(FundamentalSnapshot.validated.is_(True)).all()

    eligible_pairs: list[tuple[FundamentalSnapshot, FundamentalDocument]] = []
    skipped_future = 0
    skipped_unknown_publication = 0
    for snap, doc in joined:
        statement_day = _iso_date(str(doc.as_of or snap.as_of or ""))
        if statement_day is None or statement_day > decision:
            skipped_future += 1
            continue
        publication_day = _published_date(doc.published_at)
        if publication_day is None:
            if require_published_at:
                skipped_unknown_publication += 1
                continue
        elif publication_day > decision:
            skipped_future += 1
            continue
        eligible_pairs.append((snap, doc))

    payload, invalid_json = _latest_payload_from_rows([snap for snap, _ in eligible_pairs])

    grouped: dict[str, list[dict]] = {}
    for snap, doc in eligible_pairs:
        try:
            data = json.loads(snap.data_json)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        grouped.setdefault(str(snap.simbolo).upper(), []).append({
            "as_of": snap.as_of,
            "fiscal_period": doc.fiscal_period,
            "document_type": doc.document_type,
            "validation_score": snap.validation_score,
            "snapshot_id": snap.id,
            "data": data,
        })

    from services.fundamental_history_v5 import build_series_from_records
    histories = {symbol: build_series_from_records(records) for symbol, records in grouped.items()}
    attached = 0
    for symbol, item in list(payload.items()):
        history = histories.get(str(symbol).upper(), {})
        merged = dict(item)
        if int(history.get("history_periods_usd") or 0) > 0:
            merged.update(history)
            attached += 1
        payload[symbol] = merged

    return payload, {
        "source": "database:fundamental_snapshots:no_lookahead",
        "available": bool(payload),
        "count": len(payload),
        "invalid_json": invalid_json,
        "decision_date": decision.isoformat(),
        "require_published_at": bool(require_published_at),
        "eligible_documents": len(eligible_pairs),
        "skipped_future_or_unavailable": skipped_future,
        "skipped_unknown_publication": skipped_unknown_publication,
        "history_attached_count": attached,
        "no_lookahead": True,
    }
