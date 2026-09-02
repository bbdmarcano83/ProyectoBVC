"""Auto-revisión fail-closed para backfill fundamental V5.

Primero aplica reglas auditables específicas por emisor cuando existen; si no
resuelven el documento, usa el método genérico de misma página/columna. Nunca
fuerza una selección ambigua.
"""
from __future__ import annotations

from itertools import product
from math import isfinite

from services.fundamental_source_review_v5 import propose_issuer_specific


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


def _candidate_quality(option: dict) -> int:
    quality = str(option.get("context_quality") or "")
    return {"derived_accounting_total": 4, "accounting_row": 3, "page_fallback": 1}.get(quality, 0)


def _balance_selection(fields: dict[str, list[dict]], tolerance_pct: float = 1.0,
                       preferred_column: int | None = None) -> tuple[dict[str, int] | None, int | None]:
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
            page = arow.get("page") or lrow.get("page") or erow.get("page")
            quality = _candidate_quality(arow) + _candidate_quality(lrow) + _candidate_quality(erow)
            matches.append((error_pct, -quality, int(page or 10**9), ai, li, ei))
    if not matches:
        return None, None
    matches.sort()
    best = matches[0]
    # Equal-error/equal-quality alternatives remain ambiguous unless they are exact duplicates.
    if len(matches) > 1 and abs(matches[1][0] - best[0]) <= 0.05 and matches[1][1:3] == best[1:3]:
        if matches[1][3:] != best[3:]:
            return None, None
    ai, li, ei = best[3], best[4], best[5]
    page = int(best[2]) if best[2] < 10**9 else None
    return {
        "total_assets": _option_index(assets[ai], ai),
        "total_liabilities": _option_index(liabilities[li], li),
        "equity": _option_index(equity[ei], ei),
    }, page


_INCOME_ALIAS_PRIORITY = {
    "resultado neto del año": 100,
    "resultado neto del ejercicio": 100,
    "utilidad (pérdida) neta": 95,
    "utilidad (perdida) neta": 95,
    "ganancia (pérdida) neta": 95,
    "ganancia (perdida) neta": 95,
    "utilidad neta": 90,
    "ganancia neta": 90,
    "pérdida neta": 90,
    "perdida neta": 90,
    "resultado neto": 70,
}


def _income_near_balance(fields: dict[str, list[dict]], *, balance_page: int | None,
                         preferred_column: int | None, max_pages_after: int = 5) -> int | None:
    if balance_page is None:
        return None
    candidates = []
    for fallback, option in _filter_column(fields.get("net_income") or [], preferred_column):
        value = _num(option.get("value"))
        page = option.get("page")
        if value is None or page is None:
            continue
        try:
            page = int(page)
        except (TypeError, ValueError):
            continue
        if not (balance_page <= page <= balance_page + max_pages_after):
            continue
        if option.get("context_quality") not in {"accounting_row", "derived_accounting_total"}:
            continue
        alias = str(option.get("alias") or "").lower()
        priority = _INCOME_ALIAS_PRIORITY.get(alias, 50)
        candidates.append((page, -priority, _option_index(option, fallback), value))
    if not candidates:
        return None
    candidates.sort()
    best_page, best_priority = candidates[0][0], candidates[0][1]
    best = [c for c in candidates if c[0] == best_page and c[1] == best_priority]
    distinct = {round(c[3], 8) for c in best}
    if len(distinct) != 1:
        return None
    return best[0][2]


def propose_fail_closed_selections(review: dict) -> dict:
    if not review.get("valid"):
        return {"valid": False, "reason": "invalid_review_package", "selections": {}}

    issuer_specific = propose_issuer_specific(review)
    if issuer_specific and issuer_specific.get("valid"):
        return issuer_specific

    fields = review.get("fields") or {}
    preferred_column = review.get("preferred_column")
    try:
        preferred_column = int(preferred_column) if preferred_column is not None else None
    except (TypeError, ValueError):
        preferred_column = None

    selections: dict[str, int] = {}
    balance, balance_page = _balance_selection(fields, preferred_column=preferred_column)
    if balance:
        selections.update(balance)

    kind = str(review.get("industry_type") or "")
    if kind in {"financial", "non_financial"} and "net_income" not in selections:
        income = _income_near_balance(fields, balance_page=balance_page, preferred_column=preferred_column)
        if income is not None:
            selections["net_income"] = income

    for field, options in fields.items():
        if field in selections:
            continue
        idx = _unique_value_index(options, preferred_column=preferred_column)
        if idx is not None:
            selections[field] = idx

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
        "method": "period_header+accounting_equation+primary_income_near_balance+unique_values",
        "preferred_column": preferred_column,
        "balance_page": balance_page,
        "preferred_column_evidence": review.get("preferred_column_evidence"),
        "issuer_specific_attempted": bool(issuer_specific),
    }
