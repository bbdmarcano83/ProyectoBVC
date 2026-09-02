"""Auto-revisión fail-closed para backfill fundamental V5.

Primero aplica reglas auditables específicas por emisor cuando existen; si no
resuelven el documento, usa el método genérico de misma página/columna. Nunca
fuerza una selección ambigua.
"""
from __future__ import annotations

from itertools import product
from math import isfinite
import re
import unicodedata

from services.fundamental_source_review_v5 import propose_issuer_specific


def _num(v):
    try:
        x = float(v)
        return x if isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _norm(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def _option_index(option: dict, fallback: int) -> int:
    try:
        return int(option.get("index", fallback))
    except (TypeError, ValueError):
        return fallback


def _misclassified_component(field: str, option: dict) -> bool:
    if option.get("context_quality") == "derived_accounting_total":
        return False
    evidence = _norm(option.get("evidence"))
    if field == "total_assets":
        return any(phrase in evidence for phrase in (
            "total activo corriente", "total activos corrientes",
            "total activo no corriente", "total activos no corrientes",
            "total activo no circulante", "total activos no circulantes",
        ))
    if field == "total_liabilities":
        return any(phrase in evidence for phrase in (
            "total pasivo corriente", "total pasivos corrientes",
            "total pasivo no corriente", "total pasivos no corrientes",
            "total pasivo no circulante", "total pasivos no circulantes",
            "total pasivo a largo plazo", "total pasivos a largo plazo",
        ))
    return False


def _filtered_field(fields: dict[str, list[dict]], field: str) -> list[dict]:
    options = [o for o in (fields.get(field) or []) if isinstance(o, dict) and not _misclassified_component(field, o)]
    if field == "equity":
        exact = [o for o in options if _norm(o.get("alias")).startswith("total patrimonio") or _norm(o.get("alias")) == "patrimonio total"]
        if exact:
            return exact
    return options


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
    score = {"derived_accounting_total": 6, "accounting_row": 4, "page_fallback": 1}.get(quality, 0)
    alias = _norm(option.get("alias"))
    if alias.startswith("total del ") or alias.startswith("total patrimonio") or alias in {"total activo", "total activos", "total pasivo", "total pasivos", "patrimonio total"}:
        score += 3
    if alias == "patrimonio":
        score -= 2
    return score


def _triplet_values(assets: list[dict], liabilities: list[dict], equity: list[dict], match: tuple) -> tuple[float | None, float | None, float | None]:
    ai, li, ei = match[3], match[4], match[5]
    return _num(assets[ai].get("value")), _num(liabilities[li].get("value")), _num(equity[ei].get("value"))


def _balance_selection(fields: dict[str, list[dict]], tolerance_pct: float = 1.0,
                       preferred_column: int | None = None) -> tuple[dict[str, int] | None, int | None]:
    assets = _filtered_field(fields, "total_assets")
    liabilities = _filtered_field(fields, "total_liabilities")
    equity = _filtered_field(fields, "equity")
    matches = []
    for ai, li, ei in product(range(len(assets)), range(len(liabilities)), range(len(equity))):
        arow, lrow, erow = assets[ai], liabilities[li], equity[ei]
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
    if len(matches) > 1 and abs(matches[1][0] - best[0]) <= 0.05 and matches[1][1:3] == best[1:3]:
        first_values = _triplet_values(assets, liabilities, equity, best)
        second_values = _triplet_values(assets, liabilities, equity, matches[1])
        if first_values != second_values:
            return None, None
    ai, li, ei = best[3], best[4], best[5]
    page = int(best[2]) if best[2] < 10**9 else None
    return {
        "total_assets": _option_index(assets[ai], ai),
        "total_liabilities": _option_index(liabilities[li], li),
        "equity": _option_index(equity[ei], ei),
    }, page


_INCOME_ALIAS_PRIORITY = {
    "resultado neto del ano": 100,
    "resultado neto del ejercicio": 100,
    "utilidad perdida neta": 95,
    "ganancia perdida neta": 95,
    "utilidad neta": 90,
    "ganancia neta": 90,
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
        if option.get("context_quality") != "accounting_row":
            continue
        alias = _norm(option.get("alias"))
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
        clean_options = _filtered_field(fields, field) if field in {"total_assets", "total_liabilities", "equity"} else options
        idx = _unique_value_index(clean_options, preferred_column=preferred_column)
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
        "method": "primary_period_header+filtered_accounting_equation+primary_income_near_balance+unique_values",
        "preferred_column": preferred_column,
        "balance_page": balance_page,
        "preferred_column_evidence": review.get("preferred_column_evidence"),
        "issuer_specific_attempted": bool(issuer_specific),
    }
