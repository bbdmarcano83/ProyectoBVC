"""Auto-revisión fail-closed para backfill fundamental V5.

Sólo auto-selecciona cuando la evidencia es inequívoca. En estados comparativos
las cifras de Activos/Pasivos/Patrimonio deben pertenecer a la misma página y
columna. Nunca fuerza una selección ambigua.
"""
from __future__ import annotations

from itertools import product
from math import isfinite


def _num(v):
    try:
        x = float(v)
        return x if isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _option_index(option: dict, fallback: int) -> int:
    try:
        return int(option.get("index", fallback))
    except (TypeError, ValueError):
        return fallback


def _filter_column(options: list[dict], preferred_column: int | None) -> list[tuple[int, dict]]:
    indexed = [(i, o) for i, o in enumerate(options or []) if isinstance(o, dict)]
    if preferred_column is None:
        return indexed
    filtered = [(i, o) for i, o in indexed if o.get("column_index") == preferred_column]
    return filtered if filtered else indexed


def _unique_value_index(options: list[dict], *, rel_tol: float = 1e-9,
                        preferred_column: int | None = None) -> int | None:
    values = []
    for fallback, option in _filter_column(options, preferred_column):
        value = _num(option.get("value"))
        if value is not None:
            values.append((_option_index(option, fallback), value))
    if not values:
        return None
    base = values[0][1]
    scale = max(1.0, abs(base))
    if all(abs(v - base) <= rel_tol * scale for _, v in values[1:]):
        return values[0][0]
    return None


def _same_context(a: dict, l: dict, e: dict, preferred_column: int | None) -> bool:
    pages = {a.get("page"), l.get("page"), e.get("page")}
    pages.discard(None)
    if len(pages) > 1:
        return False
    cols = {a.get("column_index"), l.get("column_index"), e.get("column_index")}
    cols.discard(None)
    if len(cols) > 1:
        return False
    if preferred_column is not None and cols and preferred_column not in cols:
        return False
    return True


def _balance_selection(fields: dict[str, list[dict]], tolerance_pct: float = 1.0,
                       preferred_column: int | None = None) -> dict[str, int] | None:
    assets = fields.get("total_assets") or []
    liabilities = fields.get("total_liabilities") or []
    equity = fields.get("equity") or []
    matches = []
    for ai, li, ei in product(range(len(assets)), range(len(liabilities)), range(len(equity))):
        arow, lrow, erow = assets[ai], liabilities[li], equity[ei]
        if not all(isinstance(x, dict) for x in (arow, lrow, erow)):
            continue
        if not _same_context(arow, lrow, erow, preferred_column):
            continue
        a = _num(arow.get("value")); l = _num(lrow.get("value")); e = _num(erow.get("value"))
        if a is None or l is None or e is None or abs(a) < 1e-12:
            continue
        error_pct = abs(a - (l + e)) / abs(a) * 100.0
        if error_pct <= tolerance_pct:
            matches.append((error_pct, ai, li, ei))
    if not matches:
        return None
    matches.sort(key=lambda x: x[0])
    best = matches[0]
    if len(matches) > 1 and abs(matches[1][0] - best[0]) <= 0.05:
        if matches[1][1:] != best[1:]:
            return None
    ai, li, ei = best[1], best[2], best[3]
    return {
        "total_assets": _option_index(assets[ai], ai),
        "total_liabilities": _option_index(liabilities[li], li),
        "equity": _option_index(equity[ei], ei),
    }


def propose_fail_closed_selections(review: dict) -> dict:
    if not review.get("valid"):
        return {"valid": False, "reason": "invalid_review_package", "selections": {}}
    fields = review.get("fields") or {}
    preferred_column = review.get("preferred_column")
    try:
        preferred_column = int(preferred_column) if preferred_column is not None else None
    except (TypeError, ValueError):
        preferred_column = None

    selections: dict[str, int] = {}
    balance = _balance_selection(fields, preferred_column=preferred_column)
    if balance:
        selections.update(balance)

    for field, options in fields.items():
        if field in selections:
            continue
        idx = _unique_value_index(options, preferred_column=preferred_column)
        if idx is not None:
            selections[field] = idx

    kind = str(review.get("industry_type") or "")
    required = {
        "financial": {"total_assets", "equity", "net_income"},
        "non_financial": {"total_assets", "equity", "net_income"},
        "investment_vehicle": {"total_assets", "equity"},
    }.get(kind, set())
    missing = sorted(required - set(selections))
    return {
        "valid": not missing,
        "selections": selections,
        "required": sorted(required),
        "missing_required": missing,
        "reason": None if not missing else "ambiguous_or_missing_required_fields",
        "method": "same_page_same_column_accounting_equation_and_unique_values",
        "preferred_column": preferred_column,
    }
