"""Reglas de revisión específicas por emisor para estados auditados V5.

Estas reglas no relajan validación ni inventan cifras. Únicamente reducen la
ambigüedad del parser genérico usando estructura conocida del documento oficial:
- Mercantil: el estado consolidado principal aparece antes de notas/subsidiarias;
  balance principal primero y resultado neto en la sección inmediata.
- CrecePymes: los estados primarios en bolívares constantes aparecen antes del
  Anexo 18 de estados nominales; se elige la primera ecuación contable coherente.

Si el contexto sigue siendo ambiguo, se devuelve None y el registro permanece
rechazado/fail-closed.
"""
from __future__ import annotations

from itertools import product
from math import isfinite


def _num(value):
    try:
        out = float(value)
        return out if isfinite(out) else None
    except (TypeError, ValueError):
        return None


def _idx(option: dict, fallback: int) -> int:
    try:
        return int(option.get("index", fallback))
    except (TypeError, ValueError):
        return fallback


def _balance_matches(fields: dict, preferred_column: int | None, tolerance_pct: float = 1.0) -> list[dict]:
    assets = fields.get("total_assets") or []
    liabilities = fields.get("total_liabilities") or []
    equity = fields.get("equity") or []
    matches: list[dict] = []
    for ai, li, ei in product(range(len(assets)), range(len(liabilities)), range(len(equity))):
        arow, lrow, erow = assets[ai], liabilities[li], equity[ei]
        if not all(isinstance(x, dict) for x in (arow, lrow, erow)):
            continue
        pages = {arow.get("page"), lrow.get("page"), erow.get("page")}
        if None in pages or len(pages) != 1:
            continue
        cols = {arow.get("column_index"), lrow.get("column_index"), erow.get("column_index")}
        cols.discard(None)
        if len(cols) > 1:
            continue
        column = next(iter(cols)) if cols else None
        if preferred_column is not None and column is not None and column != preferred_column:
            continue
        a, l, e = _num(arow.get("value")), _num(lrow.get("value")), _num(erow.get("value"))
        if a is None or l is None or e is None or abs(a) < 1e-12:
            continue
        error = abs(a - (l + e)) / abs(a) * 100.0
        if error <= tolerance_pct:
            matches.append({
                "page": int(arow["page"]),
                "column": column,
                "error_pct": error,
                "total_assets": _idx(arow, ai),
                "total_liabilities": _idx(lrow, li),
                "equity": _idx(erow, ei),
            })
    return sorted(matches, key=lambda x: (x["page"], x["error_pct"]))


def _unique_on_earliest_page(matches: list[dict]) -> dict | None:
    if not matches:
        return None
    page = matches[0]["page"]
    earliest = [m for m in matches if m["page"] == page]
    signatures = {(m["total_assets"], m["total_liabilities"], m["equity"]) for m in earliest}
    if len(signatures) != 1:
        return None
    return earliest[0]


def _unique_income_near_balance(fields: dict, *, balance_page: int, preferred_column: int | None,
                                max_pages_after: int = 5) -> int | None:
    candidates = []
    for fallback, option in enumerate(fields.get("net_income") or []):
        if not isinstance(option, dict):
            continue
        page = option.get("page")
        value = _num(option.get("value"))
        if page is None or value is None:
            continue
        try:
            page = int(page)
        except (TypeError, ValueError):
            continue
        column = option.get("column_index")
        if preferred_column is not None and column is not None and column != preferred_column:
            continue
        if balance_page <= page <= balance_page + max_pages_after:
            candidates.append((page, _idx(option, fallback), value))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    first_page = candidates[0][0]
    first = [c for c in candidates if c[0] == first_page]
    distinct = {round(c[2], 8) for c in first}
    if len(distinct) != 1:
        return None
    return first[0][1]


def propose_issuer_specific(review: dict) -> dict | None:
    """Devuelve selecciones específicas sólo si el contexto queda inequívoco."""
    symbol = str(review.get("symbol") or "").upper().strip()
    if symbol not in {"MVZ.A", "ICP.B"}:
        return None
    fields = review.get("fields") or {}
    preferred = review.get("preferred_column")
    try:
        preferred = int(preferred) if preferred is not None else None
    except (TypeError, ValueError):
        preferred = None

    balance = _unique_on_earliest_page(_balance_matches(fields, preferred))
    if not balance:
        return None
    selections = {
        "total_assets": balance["total_assets"],
        "total_liabilities": balance["total_liabilities"],
        "equity": balance["equity"],
    }

    if symbol == "MVZ.A":
        income = _unique_income_near_balance(
            fields,
            balance_page=balance["page"],
            preferred_column=preferred,
        )
        if income is None:
            return None
        selections["net_income"] = income
        required = {"total_assets", "equity", "net_income"}
        method = "mercantil_primary_consolidated_section"
    else:
        # ICP.B es vehículo de inversión: net_income es útil pero no requerido para
        # aceptar balance. Los estados primarios constantes preceden anexos nominales.
        required = {"total_assets", "equity"}
        method = "crecepymes_primary_constant_statements_before_nominal_appendix"

    missing = sorted(required - set(selections))
    return {
        "valid": not missing,
        "selections": selections,
        "required": sorted(required),
        "missing_required": missing,
        "reason": None if not missing else "issuer_specific_required_fields_missing",
        "method": method,
        "preferred_column": preferred,
        "balance_page": balance["page"],
        "accounting_error_pct": round(float(balance["error_pct"]), 6),
    }
