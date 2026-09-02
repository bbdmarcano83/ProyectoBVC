"""Diagnóstico/backfill reproducible de períodos fundamentales V5 faltantes.

Lee la auditoría persistida, procesa únicamente períodos ausentes del manifiesto
verificado y clasifica cada resultado sin ocultar la causa. Si un documento ya
pasa todos los gates, `auto_persist` lo guarda en Neon; si no, queda fail-closed.
"""
from __future__ import annotations

import json
from collections import Counter

from scripts.audit_fundamental_documents_v5 import audit_documents
from scripts.fundamental_backfill_v5 import auto_persist


def _stage(row: dict) -> tuple[str, str | None]:
    parse = row.get("parse") if isinstance(row.get("parse"), dict) else {}
    auto = row.get("auto_review") if isinstance(row.get("auto_review"), dict) else {}
    result = row.get("result") if isinstance(row.get("result"), dict) else {}

    if parse and not parse.get("valid", True):
        return "parse", str(parse.get("error") or parse.get("reason") or "parser_invalid")
    if auto and not auto.get("valid"):
        missing = auto.get("missing_required") or []
        reason = auto.get("reason") or result.get("error") or "auto_review_rejected"
        if missing:
            reason = f"{reason}:missing={','.join(map(str, missing))}"
        return "auto_review", str(reason)
    if result.get("accepted"):
        if result.get("duplicate"):
            return "accepted_duplicate", None
        return "persisted" if result.get("persisted") else "accepted", None

    validation = result.get("validation") if isinstance(result.get("validation"), dict) else {}
    fx = result.get("fx") if isinstance(result.get("fx"), dict) else {}
    if fx and not fx.get("valid", True):
        return "fx", str(result.get("error") or fx.get("flags") or "fx_invalid")
    if validation and not validation.get("valid", True):
        return "validation", str(result.get("error") or validation.get("notes") or "accounting_validation_failed")
    return "collector", str(result.get("error") or "collector_rejected")


def diagnose_missing() -> dict:
    before = audit_documents()
    missing = [
        (item["symbol"], item["fiscal_period"])
        for item in before.get("periods", [])
        if not item.get("present")
    ]
    rows = []
    for symbol, fiscal_period in missing:
        try:
            raw = auto_persist(symbol, fiscal_period)
            stage, reason = _stage(raw)
            result = raw.get("result") if isinstance(raw.get("result"), dict) else {}
            parse = raw.get("parse") if isinstance(raw.get("parse"), dict) else {}
            auto = raw.get("auto_review") if isinstance(raw.get("auto_review"), dict) else {}
            rows.append({
                "symbol": symbol,
                "fiscal_period": fiscal_period,
                "stage": stage,
                "reason": reason,
                "accepted": bool(result.get("accepted")),
                "persisted": bool(result.get("persisted")),
                "duplicate": bool(result.get("duplicate")),
                "parser_valid": parse.get("valid"),
                "source_document_sha256": parse.get("source_document_sha256"),
                "missing_required": auto.get("missing_required") or [],
                "review_method": auto.get("method"),
            })
        except Exception as exc:
            rows.append({
                "symbol": symbol,
                "fiscal_period": fiscal_period,
                "stage": "exception",
                "reason": f"{type(exc).__name__}:{exc}",
                "accepted": False,
                "persisted": False,
                "duplicate": False,
                "parser_valid": None,
                "source_document_sha256": None,
                "missing_required": [],
                "review_method": None,
            })

    after = audit_documents()
    stage_counts = Counter(row["stage"] for row in rows)
    return {
        "database_mode": after.get("database_mode"),
        "missing_before": len(missing),
        "present_before": before.get("present_manifest_periods"),
        "present_after": after.get("present_manifest_periods"),
        "new_periods_persisted": int(after.get("present_manifest_periods", 0)) - int(before.get("present_manifest_periods", 0)),
        "expected_periods": after.get("expected_manifest_periods"),
        "stage_counts": dict(sorted(stage_counts.items())),
        "rows": rows,
    }


def main() -> int:
    report = diagnose_missing()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    # Diagnóstico puede terminar verde aunque haya rechazos; la política fail-closed
    # está en cada fila y en la auditoría estricta posterior del workflow.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
