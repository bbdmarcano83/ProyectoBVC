"""CLI persistente de backfill fundamental V5.

No existe modo dry-run. Requiere DATABASE_URL externa. Puede ejecutar un período
con selecciones explícitas o todos los pilotos con auto-revisión fail-closed.
Sólo se persisten snapshots que pasan fuente, cobertura, ecuación contable y FX.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from database import DB_PERSISTENCE_MODE, FundamentalDocument, FundamentalSnapshot, engine
from services.fundamental_autoreview_v5 import propose_fail_closed_selections
from services.fundamental_backfill_manifest_v5 import PILOT_BACKFILL_V5
from services.fundamental_pdf_parser_v5 import fetch_and_parse_official_pdf
from services.fundamental_review_v5 import build_review_package, accept_reviewed_snapshot


def _require_external_db() -> None:
    if DB_PERSISTENCE_MODE != "external":
        raise RuntimeError("external_database_required_for_persistent_backfill")


def _ensure_v5_fundamental_schema() -> None:
    FundamentalDocument.__table__.create(bind=engine, checkfirst=True)
    FundamentalSnapshot.__table__.create(bind=engine, checkfirst=True)


def _document(symbol: str, period: str) -> dict:
    issuer = PILOT_BACKFILL_V5.get(symbol)
    if not issuer:
        raise SystemExit(f"Símbolo no incluido en piloto: {symbol}")
    doc = next((d for d in issuer.get("documents", []) if d.get("fiscal_period") == period), None)
    if not doc:
        raise SystemExit(f"Período no registrado: {symbol} {period}")
    if not doc.get("url"):
        raise SystemExit(f"Documento sin URL exacta: {symbol} {period}")
    return {**doc, "industry_type": issuer.get("industry_type"), "issuer": issuer.get("issuer")}


def _preferred_column(doc: dict) -> int:
    kind = str(doc.get("document_type") or "")
    if kind == "comparative_in_2024_audit":
        return 1
    return 0


def _monetary_basis(symbol: str) -> str:
    symbol = str(symbol or "").upper().strip()
    if symbol in {"SVS", "ICP.B"}:
        return "constant_ves_end_period"
    return "nominal_ves"


def build_review(symbol: str, period: str) -> dict:
    doc = _document(symbol, period)
    candidates, parse_meta = fetch_and_parse_official_pdf(symbol, doc["url"])
    review = build_review_package(
        symbol,
        candidates,
        source_url=doc["url"],
        as_of=doc["as_of"],
        source_document_sha256=parse_meta.get("source_document_sha256"),
    )
    review["preferred_column"] = _preferred_column(doc)
    return {"document": doc, "parse": parse_meta, "review": review}


def _persist_review(package: dict, payload: dict) -> dict:
    review = package["review"]
    if not review.get("valid"):
        return {"accepted": False, "error": "review_package_invalid", "package": package}
    selections = payload.get("selections") if isinstance(payload, dict) else None
    if not isinstance(selections, dict):
        return {"accepted": False, "error": "selections_required"}
    extra_fields = payload.get("extra_fields", {}) if isinstance(payload, dict) else {}
    doc = package["document"]
    result = accept_reviewed_snapshot(
        review,
        selections,
        document_type=doc["document_type"],
        fiscal_period=doc["fiscal_period"],
        audited=bool(doc.get("audited")),
        currency=str(payload.get("currency") or "VES"),
        monetary_basis=str(payload.get("monetary_basis") or _monetary_basis(review.get("symbol"))),
        period_start=payload.get("period_start"),
        published_at=payload.get("published_at") or doc.get("published_at"),
        extra_fields=extra_fields,
        hydrate_fx=True,
        require_fx=True,
    )
    return {"document": doc, "parse": package["parse"], "result": result}


def accept(symbol: str, period: str, selections_path: str) -> dict:
    _require_external_db()
    _ensure_v5_fundamental_schema()
    package = build_review(symbol, period)
    payload = json.loads(Path(selections_path).read_text(encoding="utf-8"))
    return _persist_review(package, payload)


def auto_persist(symbol: str, period: str) -> dict:
    _require_external_db()
    _ensure_v5_fundamental_schema()
    package = build_review(symbol, period)
    review = package["review"]
    proposal = propose_fail_closed_selections(review)
    if not proposal.get("valid"):
        return {
            "document": package["document"],
            "parse": package["parse"],
            "auto_review": proposal,
            "result": {"accepted": False, "persisted": False, "error": proposal.get("reason")},
        }
    payload = {
        "selections": proposal["selections"],
        "currency": "VES",
        "monetary_basis": _monetary_basis(symbol),
        "extra_fields": {},
    }
    out = _persist_review(package, payload)
    out["auto_review"] = proposal
    return out


def auto_persist_all() -> dict:
    _require_external_db()
    _ensure_v5_fundamental_schema()
    rows = []
    accepted = rejected = persisted = 0
    for symbol, issuer in PILOT_BACKFILL_V5.items():
        for doc in issuer.get("documents", []):
            period = str(doc.get("fiscal_period") or "")
            try:
                row = auto_persist(symbol, period)
            except Exception as exc:
                row = {
                    "document": {"symbol": symbol, "fiscal_period": period},
                    "result": {"accepted": False, "persisted": False, "error": type(exc).__name__},
                }
            result = row.get("result") or {}
            if result.get("accepted"):
                accepted += 1
            else:
                rejected += 1
            if result.get("persisted"):
                persisted += 1
            rows.append(row)
    return {
        "database_mode": DB_PERSISTENCE_MODE,
        "documents": len(rows),
        "accepted": accepted,
        "rejected": rejected,
        "persisted": persisted,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Caracas Bull V5 persistent fundamental backfill")
    parser.add_argument("--symbol")
    parser.add_argument("--period")
    parser.add_argument("--accept", help="JSON con selections explícitas")
    parser.add_argument("--all", action="store_true", help="Procesa los 12 documentos piloto con auto-revisión fail-closed")
    args = parser.parse_args()

    if args.all:
        output = auto_persist_all()
        ok = output.get("accepted", 0) > 0
    else:
        if not args.symbol or not args.period:
            parser.error("--symbol y --period son requeridos salvo con --all")
        symbol = args.symbol.upper().strip()
        output = accept(symbol, args.period, args.accept) if args.accept else auto_persist(symbol, args.period)
        ok = bool((output.get("result") or {}).get("accepted"))

    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
