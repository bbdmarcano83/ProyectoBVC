"""Backfill de net_income sólo cuando la fila certificada es inequívoca.

No contiene cifras financieras. Resuelve el índice por semántica exacta de la
fila contable, columna vigente y página principal; luego reutiliza todos los
gates normales de certificación, FX, contabilidad y persistencia.
"""
from __future__ import annotations

import json
import unicodedata

from scripts.fundamental_backfill_v5 import build_review, _persist_review
from services.fundamental_autoreview_v5 import propose_fail_closed_selections

TARGETS = (
    ("ABC.A", "FY2022"),
    ("BPV", "FY2023"),
    ("BPV", "FY2024"),
    ("BPV", "FY2025"),
    ("IVC.A", "FY2024"),
    ("IVC.A", "FY2025"),
)


def _norm(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().split())


def _candidate_matches(symbol: str, option: dict, preferred_column: int | None) -> bool:
    if option.get("context_quality") != "accounting_row":
        return False
    if preferred_column is not None and option.get("column_index") != preferred_column:
        return False
    ev = _norm(option.get("evidence"))
    alias = _norm(option.get("alias"))
    if symbol == "BPV":
        return alias == "resultado neto" and ev.startswith("resultado neto del ejercicio ")
    if symbol == "ABC.A":
        return alias == "utilidad neta" and ev.startswith("utilidad neta ")
    if symbol == "IVC.A":
        if "integral" in ev:
            return False
        return (
            alias in {"utilidad neta", "perdida neta"}
            and (ev.startswith("(perdida) utilidad neta ") or ev.startswith("perdida neta "))
        )
    return False


def resolve_exact_net_income(review: dict, proposal: dict) -> dict:
    symbol = str(review.get("symbol") or "").upper()
    missing = list(proposal.get("missing_required") or [])
    if missing != ["net_income"]:
        return {"valid": False, "reason": "net_income_not_only_missing_field", "missing_required": missing}

    preferred = review.get("preferred_column")
    options = review.get("fields", {}).get("net_income") or []
    matches = [o for o in options if _candidate_matches(symbol, o, preferred)]
    if not matches:
        return {"valid": False, "reason": "exact_certified_net_income_row_not_found"}

    pages = [int(o.get("page")) for o in matches if o.get("page") is not None]
    if not pages:
        return {"valid": False, "reason": "exact_row_has_no_page"}
    primary_page = min(pages)
    primary = [o for o in matches if int(o.get("page")) == primary_page]
    values = []
    for option in primary:
        try:
            values.append(float(option.get("value")))
        except (TypeError, ValueError):
            return {"valid": False, "reason": "exact_row_has_invalid_value"}
    if not values:
        return {"valid": False, "reason": "exact_row_has_no_value"}
    base = values[0]
    tolerance = max(1.0, abs(base)) * 1e-9
    if any(abs(value - base) > tolerance for value in values[1:]):
        return {"valid": False, "reason": "certified_exact_row_value_conflict", "page": primary_page}

    chosen = primary[0]
    selections = dict(proposal.get("selections") or {})
    selections["net_income"] = int(chosen["index"])
    return {
        "valid": True,
        "selections": selections,
        "method": "certified_exact_accounting_row+preferred_period_column+primary_page",
        "page": primary_page,
        "candidate_index": int(chosen["index"]),
        "evidence": chosen.get("evidence"),
    }


def persist_one(symbol: str, period: str) -> dict:
    package = build_review(symbol, period)
    review = package.get("review") or {}
    proposal = propose_fail_closed_selections(review)
    exact = resolve_exact_net_income(review, proposal)
    if not exact.get("valid"):
        return {"symbol": symbol, "fiscal_period": period, "accepted": False, "persisted": False, "resolution": exact}
    doc = package["document"]
    payload = {
        "selections": exact["selections"],
        "currency": doc.get("currency", "VES"),
        "monetary_basis": doc.get("monetary_basis"),
        "period_start": doc.get("period_start"),
        "extra_fields": {},
    }
    out = _persist_review(package, payload)
    result = out.get("result") if isinstance(out.get("result"), dict) else {}
    return {
        "symbol": symbol,
        "fiscal_period": period,
        "accepted": bool(result.get("accepted")),
        "persisted": bool(result.get("persisted")),
        "duplicate": bool(result.get("duplicate")),
        "document_id": result.get("document_id"),
        "snapshot_id": result.get("snapshot_id"),
        "resolution": exact,
        "certification": result.get("certification"),
        "fx": result.get("fx"),
        "coverage": result.get("coverage"),
        "validation": result.get("validation"),
        "error": result.get("error"),
    }


def main() -> int:
    rows = []
    for symbol, period in TARGETS:
        try:
            rows.append(persist_one(symbol, period))
        except Exception as exc:
            rows.append({"symbol": symbol, "fiscal_period": period, "accepted": False, "persisted": False, "error": f"{type(exc).__name__}:{exc}"})
    accepted = sum(1 for row in rows if row.get("accepted"))
    report = {"targets": len(TARGETS), "accepted": accepted, "all_accepted": accepted == len(TARGETS), "rows": rows}
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["all_accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
